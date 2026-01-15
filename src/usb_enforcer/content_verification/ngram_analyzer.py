"""
N-gram analysis for content scanning.

Provides character and word n-gram analysis to detect obfuscated or
formatted sensitive data that might not match exact regex patterns.
"""

import re
import logging
from typing import Set, List, Tuple
from collections import defaultdict


logger = logging.getLogger(__name__)


class NgramAnalyzer:
    """
    N-gram analyzer for detecting suspicious patterns.
    
    Uses character trigrams and word bigrams to identify potentially
    sensitive content even when formats vary.
    """
    
    # Sensitive word bigrams that indicate PII/financial data
    SENSITIVE_BIGRAMS = {
        ('social', 'security'),
        ('credit', 'card'),
        ('date', 'birth'),
        ('driver', 'license'),
        ('driver\'s', 'license'),
        ('passport', 'number'),
        ('tax', 'id'),
        ('patient', 'id'),
        ('medical', 'record'),
        ('bank', 'account'),
        ('account', 'number'),
        ('routing', 'number'),
        ('api', 'key'),
        ('secret', 'key'),
        ('access', 'token'),
        ('private', 'key'),
        ('password', 'is'),
        ('ssn', 'is'),
        ('employee', 'id'),
        ('national', 'identifier'),
    }
    
    def __init__(self, char_ngram_size: int = 3, word_ngram_size: int = 2):
        """
        Initialize n-gram analyzer.
        
        Args:
            char_ngram_size: Size of character n-grams (default: 3 for trigrams)
            word_ngram_size: Size of word n-grams (default: 2 for bigrams)
        """
        self.char_ngram_size = char_ngram_size
        self.word_ngram_size = word_ngram_size
        
        # Build digit trigram set for detecting numeric patterns
        self.digit_trigrams = self._build_digit_trigrams()
    
    def _build_digit_trigrams(self) -> Set[str]:
        """Build set of trigrams from digit sequences"""
        trigrams = set()
        
        # Common digit patterns in SSNs, credit cards, etc.
        digit_sequences = [
            '0123456789',
            '9876543210',
            '1234567890',
        ]
        
        for seq in digit_sequences:
            for i in range(len(seq) - self.char_ngram_size + 1):
                trigram = seq[i:i + self.char_ngram_size]
                trigrams.add(trigram)
        
        return trigrams
    
    def extract_char_ngrams(self, text: str) -> List[str]:
        """
        Extract character n-grams from text.
        
        Args:
            text: Text to analyze
            
        Returns:
            List of character n-grams
        """
        # Focus on digit sequences
        digit_text = re.sub(r'[^\d]', '', text)
        
        ngrams = []
        for i in range(len(digit_text) - self.char_ngram_size + 1):
            ngram = digit_text[i:i + self.char_ngram_size]
            ngrams.append(ngram)
        
        return ngrams
    
    def extract_word_ngrams(self, text: str) -> List[Tuple[str, ...]]:
        """
        Extract word n-grams from text.
        
        Args:
            text: Text to analyze
            
        Returns:
            List of word n-gram tuples
        """
        # Tokenize into words
        words = re.findall(r'\b\w+\b', text.lower())
        
        ngrams = []
        for i in range(len(words) - self.word_ngram_size + 1):
            ngram = tuple(words[i:i + self.word_ngram_size])
            ngrams.append(ngram)
        
        return ngrams
    
    def calculate_char_ngram_score(self, text: str) -> float:
        """
        Calculate suspicion score based on character n-grams.
        
        Looks for high density of sequential digit trigrams which
        suggests SSNs, credit cards, etc.
        
        Args:
            text: Text to analyze
            
        Returns:
            Score from 0.0 (not suspicious) to 1.0 (highly suspicious)
        """
        char_ngrams = self.extract_char_ngrams(text)
        
        if not char_ngrams:
            return 0.0
        
        # Count how many trigrams match known digit patterns
        matches = sum(1 for ngram in char_ngrams if ngram in self.digit_trigrams)
        
        # Calculate density
        density = matches / len(char_ngrams)
        
        logger.debug(f"Character n-gram score: {density:.3f} ({matches}/{len(char_ngrams)} matches)")
        
        return density
    
    def calculate_word_ngram_score(self, text: str) -> float:
        """
        Calculate suspicion score based on word n-grams.
        
        Looks for sensitive word combinations like "social security",
        "credit card", etc.
        
        Args:
            text: Text to analyze
            
        Returns:
            Score from 0.0 (not suspicious) to 1.0 (highly suspicious)
        """
        word_ngrams = self.extract_word_ngrams(text)
        
        if not word_ngrams:
            return 0.0
        
        # Count matches with sensitive bigrams
        matches = sum(1 for ngram in word_ngrams if ngram in self.SENSITIVE_BIGRAMS)
        
        if matches == 0:
            return 0.0
        
        # Calculate score - even one match is significant
        # But multiple matches increase confidence
        score = min(1.0, 0.5 + (matches * 0.2))
        
        logger.debug(f"Word n-gram score: {score:.3f} ({matches} sensitive bigrams)")
        
        return score
    
    def score_content(self, text: str) -> float:
        """
        Calculate overall suspicion score for content.
        
        Combines character and word n-gram scores with appropriate weighting.
        
        Args:
            text: Text to analyze
            
        Returns:
            Overall suspicion score from 0.0 to 1.0
        """
        char_score = self.calculate_char_ngram_score(text)
        word_score = self.calculate_word_ngram_score(text)
        
        # Word matches are more reliable indicators
        # Weight: 40% char, 60% word
        overall_score = (char_score * 0.4) + (word_score * 0.6)
        
        logger.debug(f"N-gram overall score: {overall_score:.3f} (char: {char_score:.3f}, word: {word_score:.3f})")
        
        return overall_score
    
    def is_suspicious(self, text: str, threshold: float = 0.65) -> bool:
        """
        Determine if text is suspicious based on n-gram analysis.
        
        Args:
            text: Text to analyze
            threshold: Suspicion threshold (default: 0.65)
            
        Returns:
            True if suspicion score exceeds threshold
        """
        score = self.score_content(text)
        return score >= threshold


class EntropyAnalyzer:
    """
    Entropy analyzer for detecting high-entropy content.
    
    High entropy can indicate encrypted data, compressed data,
    or encoded secrets (base64, hex, etc.)
    """
    
    def __init__(self, threshold: float = 7.5, block_size: int = 1024):
        """
        Initialize entropy analyzer.
        
        Args:
            threshold: Entropy threshold (0-8 bits, default: 7.5)
            block_size: Size of blocks to analyze in bytes
        """
        self.threshold = threshold
        self.block_size = block_size
    
    def calculate_entropy(self, data: bytes) -> float:
        """
        Calculate Shannon entropy of data.
        
        Args:
            data: Byte data to analyze
            
        Returns:
            Entropy value (0.0 to 8.0 bits per byte)
        """
        if not data:
            return 0.0
        
        # Count byte frequencies
        frequencies = defaultdict(int)
        for byte in data:
            frequencies[byte] += 1
        
        # Calculate entropy
        import math
        entropy = 0.0
        data_len = len(data)
        
        for count in frequencies.values():
            if count > 0:
                probability = count / data_len
                entropy -= probability * math.log2(probability)
        
        return entropy
    
    def analyze_content(self, data: bytes) -> Tuple[float, bool]:
        """
        Analyze content for high entropy.
        
        Args:
            data: Byte data to analyze
            
        Returns:
            Tuple of (max_entropy, is_suspicious)
        """
        if len(data) <= self.block_size:
            # Analyze entire content
            entropy = self.calculate_entropy(data)
            suspicious = entropy >= self.threshold
            
            logger.debug(f"Entropy: {entropy:.3f} bits/byte (threshold: {self.threshold})")
            
            return entropy, suspicious
        
        # Analyze in blocks and find maximum
        max_entropy = 0.0
        
        for i in range(0, len(data), self.block_size):
            block = data[i:i + self.block_size]
            entropy = self.calculate_entropy(block)
            max_entropy = max(max_entropy, entropy)
            
            # Early exit if threshold exceeded
            if entropy >= self.threshold:
                logger.debug(f"High entropy detected: {entropy:.3f} bits/byte at block {i // self.block_size}")
                return entropy, True
        
        logger.debug(f"Max entropy: {max_entropy:.3f} bits/byte (threshold: {self.threshold})")
        
        return max_entropy, False
    
    def is_encrypted_or_compressed(self, data: bytes) -> bool:
        """
        Check if data appears to be encrypted or compressed.
        
        Args:
            data: Byte data to check
            
        Returns:
            True if high entropy suggests encryption/compression
        """
        _, suspicious = self.analyze_content(data)
        return suspicious
