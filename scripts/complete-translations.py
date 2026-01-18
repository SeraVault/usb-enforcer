#!/usr/bin/env python3
"""Complete Spanish and French translations for USB Enforcer Admin"""

import re
import sys

# Comprehensive Spanish translations
spanish_translations = {
    # Multi-line error messages
    "Error loading configuration: {}\\nUsing default configuration.": 
        "Error al cargar la configuración: {}\\nUsando configuración predeterminada.",
    
    # Multi-line descriptions
    "When enabled, only USB devices are subject to enforcement. Other storage devices (SATA, NVMe) are not affected.":
        "Cuando está habilitado, solo los dispositivos USB están sujetos a la aplicación. Otros dispositivos de almacenamiento (SATA, NVMe) no se ven afectados.",
    
    "Allow older LUKS1 encrypted devices in read-only mode. LUKS2 is recommended for better security.":
        "Permitir dispositivos cifrados LUKS1 antiguos en modo de solo lectura. Se recomienda LUKS2 para mayor seguridad.",
    
    "Allow write access to unencrypted USB drives when content scanning is enabled. Files are scanned for sensitive data before writing.":
        "Permitir acceso de escritura a unidades USB sin cifrar cuando el escaneo de contenido está habilitado. Los archivos se escanean en busca de datos sensibles antes de escribir.",
    
    "Minimum number of characters required for encryption passphrases. Recommended: 12 or higher.":
        "Número mínimo de caracteres requeridos para contraseñas de cifrado. Recomendado: 12 o más.",
    
    "Linux groups that are exempt from USB enforcement. Users in these groups can use any USB devices without restrictions. Enter one group name per line.":
        "Grupos de Linux que están exentos de la aplicación USB. Los usuarios en estos grupos pueden usar cualquier dispositivo USB sin restricciones. Ingrese un nombre de grupo por línea.",
    
    "Time-to-live for one-time tokens used in passphrase handoff. After this time, tokens expire and cannot be used.":
        "Tiempo de vida para tokens de un solo uso utilizados en la transferencia de contraseña. Después de este tiempo, los tokens expiran y no se pueden usar.",
    
    "Maximum number of tokens kept in memory at once. Prevents memory exhaustion from token spam.":
        "Número máximo de tokens mantenidos en memoria a la vez. Previene el agotamiento de memoria por spam de tokens.",
    
    "Mount options for unencrypted USB devices. Recommended: nodev, nosuid, noexec, ro":
        "Opciones de montaje para dispositivos USB sin cifrar. Recomendado: nodev, nosuid, noexec, ro",
    
    "Prevent execution of binaries from unencrypted USB devices. Recommended for security.":
        "Prevenir la ejecución de binarios de dispositivos USB sin cifrar. Recomendado para seguridad.",
    
    "luks2: Linux Unified Key Setup (Linux only)\\nveracrypt: VeraCrypt (Cross-platform: Windows/Mac/Linux)\\nNote: VeraCrypt must be installed separately":
        "luks2: Linux Unified Key Setup (solo Linux)\\nveracrypt: VeraCrypt (multiplataforma: Windows/Mac/Linux)\\nNota: VeraCrypt debe instalarse por separado",
    
    "whole_disk: Encrypt entire disk\\npartition: Encrypt specific partition only":
        "whole_disk: Cifrar disco completo\\npartition: Cifrar solo partición específica",
    
    "Filesystem to use after encryption:\\nexfat: Cross-platform (Windows/Mac/Linux)\\next4: Linux native, journaling\\nntfs: Windows-focused":
        "Sistema de archivos a usar después del cifrado:\\nexfat: Multiplataforma (Windows/Mac/Linux)\\next4: Nativo de Linux, con journaling\\nntfs: Enfocado en Windows",
    
    "argon2id: Recommended, resistant to GPU attacks\\npbkdf2: Older, less secure":
        "argon2id: Recomendado, resistente a ataques de GPU\\npbkdf2: Más antiguo, menos seguro",
    
    "aes-xts-plain64: Recommended for disk encryption\\naes-cbc-essiv:sha256: Older algorithm":
        "aes-xts-plain64: Recomendado para cifrado de disco\\naes-cbc-essiv:sha256: Algoritmo más antiguo",
    
    "512: Maximum security (recommended)\\n256: Standard security":
        "512: Seguridad máxima (recomendado)\\n256: Seguridad estándar",
    
    "Enable real-time scanning of files for sensitive data. Prevents writing credit cards, SSNs, API keys, etc. to USB devices.":
        "Habilitar el escaneo en tiempo real de archivos para datos sensibles. Previene la escritura de tarjetas de crédito, SSN, claves API, etc. en dispositivos USB.",
    
    "When enabled, scanning applies to both encrypted and unencrypted devices. When disabled, scanning only applies to unencrypted devices.":
        "Cuando está habilitado, el escaneo se aplica a dispositivos cifrados y sin cifrar. Cuando está deshabilitado, el escaneo solo se aplica a dispositivos sin cifrar.",
    
    "block: Prevent writing files with sensitive data\\nwarn: Allow write but show warning\\nlog_only: Allow write and log to journal":
        "block: Prevenir la escritura de archivos con datos sensibles\\nwarn: Permitir escritura pero mostrar advertencia\\nlog_only: Permitir escritura y registrar en el diario",
    
    "Maximum file size to scan (0 = unlimited). Larger files may be skipped or sampled based on oversize_action.":
        "Tamaño máximo de archivo a escanear (0 = ilimitado). Los archivos más grandes pueden omitirse o muestrearse según oversize_action.",
    
    "block: Block files exceeding max size\\nallow_unscanned: Allow without scanning":
        "block: Bloquear archivos que excedan el tamaño máximo\\nallow_unscanned: Permitir sin escanear",
    
    "Files larger than this are written to temp disk before scanning. 0 = always stream to disk.":
        "Los archivos más grandes que esto se escriben en disco temporal antes del escaneo. 0 = siempre transmitir a disco.",
    
    "full: Scan entire file contents\\nsampled: Sample portions of large files":
        "full: Escanear todo el contenido del archivo\\nsampled: Muestrear porciones de archivos grandes",
    
    "Extract and scan files inside archive files. Prevents hiding sensitive data in compressed files.":
        "Extraer y escanear archivos dentro de archivos comprimidos. Previene ocultar datos sensibles en archivos comprimidos.",
    
    "Maximum nesting level for archives (e.g., ZIP inside ZIP). Prevents zip bomb attacks.":
        "Nivel máximo de anidamiento para archivos (por ejemplo, ZIP dentro de ZIP). Previene ataques de bomba zip.",
    
    "Use machine learning for pattern detection in unstructured text. Helps detect obfuscated or formatted sensitive data.":
        "Usar aprendizaje automático para detección de patrones en texto no estructurado. Ayuda a detectar datos sensibles ofuscados o formateados.",
    
    "Cache scan results based on file hash. Improves performance for repeated scans of same files.":
        "Almacenar en caché los resultados del escaneo basados en el hash del archivo. Mejora el rendimiento para escaneos repetidos de los mismos archivos.",
    
    "When enabled, only USB devices are enforced. Other storage types (SATA, NVMe, etc.) are not affected. Useful for workstations where internal drives should not be restricted.":
        "Cuando está habilitado, solo se aplican los dispositivos USB. Otros tipos de almacenamiento (SATA, NVMe, etc.) no se ven afectados. Útil para estaciones de trabajo donde las unidades internas no deben estar restringidas.",
    
    "LUKS1 is an older encryption format. If enabled, LUKS1 devices are allowed but only in read-only mode. LUKS2 is more secure and should be preferred.":
        "LUKS1 es un formato de cifrado más antiguo. Si está habilitado, los dispositivos LUKS1 están permitidos pero solo en modo de solo lectura. LUKS2 es más seguro y debe ser preferido.",
    
    "Allows writing to unencrypted USB drives if content scanning is enabled. Files are scanned for sensitive patterns before being written. Requires content_scanning_enabled=true.":
        "Permite escribir en unidades USB sin cifrar si el escaneo de contenido está habilitado. Los archivos se escanean en busca de patrones sensibles antes de ser escritos. Requiere content_scanning_enabled=true.",
    
    "Users in the configured exemption group can bypass enforcement. Useful for IT administrators or trusted users who need unrestricted access.":
        "Los usuarios en el grupo de exención configurado pueden evitar la aplicación. Útil para administradores de TI o usuarios de confianza que necesitan acceso sin restricciones.",
    
    "Name of the system group whose members are exempt from enforcement. Default is 'usb-exempt'. Create this group and add trusted users to it.":
        "Nombre del grupo del sistema cuyos miembros están exentos de la aplicación. El valor predeterminado es 'usb-exempt'. Cree este grupo y agregue usuarios de confianza a él.",
    
    "Mount options for unencrypted USB devices, one per line. Common options:\\n• nodev - No device files\\n• nosuid - Ignore setuid bits\\n• noexec - Prevent execution\\n• ro - Read-only\\nRecommended: nodev, nosuid, noexec, ro":
        "Opciones de montaje para dispositivos USB sin cifrar, una por línea. Opciones comunes:\\n• nodev - Sin archivos de dispositivo\\n• nosuid - Ignorar bits setuid\\n• noexec - Prevenir ejecución\\n• ro - Solo lectura\\nRecomendado: nodev, nosuid, noexec, ro",
    
    "Mount options for encrypted USB devices, one per line. Common options:\\n• nodev - No device files\\n• nosuid - Ignore setuid bits\\n• rw - Read-write access\\nRecommended: nodev, nosuid, rw":
        "Opciones de montaje para dispositivos USB cifrados, una por línea. Opciones comunes:\\n• nodev - Sin archivos de dispositivo\\n• nosuid - Ignorar bits setuid\\n• rw - Acceso de lectura-escritura\\nRecomendado: nodev, nosuid, rw",
    
    "Enforce noexec flag on unencrypted USB drives. Prevents running executables from plaintext USB devices. Strongly recommended for security.":
        "Aplicar bandera noexec en unidades USB sin cifrar. Previene la ejecución de ejecutables desde dispositivos USB de texto plano. Fuertemente recomendado para seguridad.",
    
    "Forces all allowed devices to be mounted read-only. Prevents any writes even if the device would normally allow them. Highest security option.":
        "Fuerza que todos los dispositivos permitidos se monten en solo lectura. Previene cualquier escritura incluso si el dispositivo normalmente lo permitiría. Opción de mayor seguridad.",
    
    "Additional mount options passed to the kernel. Common options include 'noexec' (prevent execution), 'nosuid' (ignore setuid), 'nodev' (no device files).":
        "Opciones de montaje adicionales pasadas al kernel. Las opciones comunes incluyen 'noexec' (prevenir ejecución), 'nosuid' (ignorar setuid), 'nodev' (sin archivos de dispositivo).",
    
    "Default encryption format for new USB devices. LUKS2 is Linux-only and recommended for Linux environments. VeraCrypt is cross-platform (Windows/Mac/Linux) but requires separate installation from https://www.veracrypt.fr":
        "Formato de cifrado predeterminado para nuevos dispositivos USB. LUKS2 es solo para Linux y se recomienda para entornos Linux. VeraCrypt es multiplataforma (Windows/Mac/Linux) pero requiere instalación separada desde https://www.veracrypt.fr",
    
    "Determines what gets encrypted. 'whole_disk' encrypts the entire device (recommended). 'partition' only encrypts a specific partition.":
        "Determina qué se cifra. 'whole_disk' cifra todo el dispositivo (recomendado). 'partition' solo cifra una partición específica.",
    
    "Filesystem created on encrypted devices. exfat is cross-platform. ext4 is Linux-native with journaling. ntfs is Windows-focused.":
        "Sistema de archivos creado en dispositivos cifrados. exfat es multiplataforma. ext4 es nativo de Linux con journaling. ntfs está enfocado en Windows.",
    
    "Cipher algorithm for LUKS2 encryption. aes-xts-plain64 is recommended for modern systems. Options: aes-xts-plain64, aes-cbc-essiv, serpent-xts-plain64.":
        "Algoritmo de cifrado para cifrado LUKS2. aes-xts-plain64 es recomendado para sistemas modernos. Opciones: aes-xts-plain64, aes-cbc-essiv, serpent-xts-plain64.",
    
    "Encryption key size in bits. 512 = 256-bit effective (XTS mode uses half for tweak). Larger is more secure but may be slightly slower.":
        "Tamaño de clave de cifrado en bits. 512 = efectivo de 256 bits (modo XTS usa la mitad para ajuste). Más grande es más seguro pero puede ser ligeramente más lento.",
    
    "Hash algorithm for key derivation. sha256 is standard, sha512 is more secure but slower. Options: sha256, sha512.":
        "Algoritmo hash para derivación de clave. sha256 es estándar, sha512 es más seguro pero más lento. Opciones: sha256, sha512.",
    
    "Password-based key derivation function. argon2id is most secure (resistant to GPU attacks). Options: argon2id, argon2i, pbkdf2.":
        "Función de derivación de clave basada en contraseña. argon2id es más seguro (resistente a ataques GPU). Opciones: argon2id, argon2i, pbkdf2.",
    
    "Time in milliseconds for key derivation. Higher values are more secure (slower brute force) but take longer to unlock. 2000ms is recommended.":
        "Tiempo en milisegundos para derivación de clave. Valores más altos son más seguros (fuerza bruta más lenta) pero tardan más en desbloquear. Se recomienda 2000ms.",
    
    "Minimum length for auto-generated passphrases. Longer is more secure. 32 characters provides excellent security.":
        "Longitud mínima para contraseñas generadas automáticamente. Más largo es más seguro. 32 caracteres proporciona una excelente seguridad.",
    
    "Enables content scanning (DLP) to detect sensitive data patterns like SSNs, credit cards, etc. Requires patterns to be configured.":
        "Habilita el escaneo de contenido (DLP) para detectar patrones de datos sensibles como SSN, tarjetas de crédito, etc. Requiere que se configuren los patrones.",
    
    "Detect US Social Security Numbers (XXX-XX-XXXX format).":
        "Detectar números de Seguro Social de EE. UU. (formato XXX-XX-XXXX).",
    
    "Detect credit card numbers using Luhn algorithm validation.":
        "Detectar números de tarjetas de crédito usando validación de algoritmo Luhn.",
    
    "Detect email addresses.":
        "Detectar direcciones de correo electrónico.",
    
    "Detect US phone numbers in various formats.":
        "Detectar números de teléfono de EE. UU. en varios formatos.",
    
    "Use custom regex patterns defined in the configuration.":
        "Usar patrones regex personalizados definidos en la configuración.",
    
    "Maximum size of files to scan. Larger files are skipped to prevent performance issues. 100MB is reasonable for most use cases.":
        "Tamaño máximo de archivos a escanear. Los archivos más grandes se omiten para prevenir problemas de rendimiento. 100MB es razonable para la mayoría de los casos de uso.",
    
    "Maximum time to spend scanning a single file. Prevents hangs on malformed files. 30 seconds is typical.":
        "Tiempo máximo para escanear un solo archivo. Previene bloqueos en archivos mal formados. 30 segundos es típico.",
    
    "Scan inside ZIP and other archive files. Increases scan time but catches hidden data.":
        "Escanear dentro de archivos ZIP y otros archivos. Aumenta el tiempo de escaneo pero captura datos ocultos.",
    
    "How many levels deep to scan nested archives. Prevents zip bombs. 3 levels is reasonable.":
        "Cuántos niveles de profundidad escanear archivos anidados. Previene bombas zip. 3 niveles es razonable.",
    
    "Use machine learning models for anomaly detection. Requires trained models to be present.":
        "Usar modelos de aprendizaje automático para detección de anomalías. Requiere que estén presentes modelos entrenados.",
}

# Comprehensive French translations
french_translations = {
    "Minimum passphrase length should be at least 8 characters":
        "La longueur minimale de la phrase secrète doit être d'au moins 8 caractères",
    
    "Maximum passphrase length should not exceed 128 characters":
        "La longueur maximale de la phrase secrète ne doit pas dépasser 128 caractères",
    
    "TTL should be at least 60 seconds":
        "Le TTL doit être d'au moins 60 secondes",
    
    "TTL should not exceed 3600 seconds (1 hour)":
        "Le TTL ne doit pas dépasser 3600 secondes (1 heure)",
    
    "Max tokens should be at least 16":
        "Les jetons maximum doivent être au moins 16",
    
    "Max tokens should not exceed 1024":
        "Les jetons maximum ne doivent pas dépasser 1024",
    
    "File size cannot be negative (use 0 for unlimited)":
        "La taille du fichier ne peut pas être négative (utilisez 0 pour illimité)",
    
    "File size limit should not exceed 10240 MB (10 GB)":
        "La limite de taille de fichier ne doit pas dépasser 10240 Mo (10 Go)",
    
    "Timeout should be at least 5 seconds":
        "Le délai d'attente doit être d'au moins 5 secondes",
    
    "Timeout should not exceed 300 seconds":
        "Le délai d'attente ne doit pas dépasser 300 secondes",
    
    "Close": "Fermer",
    "USB Enforcer Administration": "Administration d'USB Enforcer",
    "USB Enforcer Configuration": "Configuration d'USB Enforcer",
    "Save Configuration": "Enregistrer la Configuration",
    "Restart Daemon": "Redémarrer le Démon",
    "Restart usb-enforcerd to reload configuration": "Redémarrer usb-enforcerd pour recharger la configuration",
    "Documentation": "Documentation",
    "Administration Guide": "Guide d'Administration",
    "Content Scanning": "Analyse de Contenu",
    "Anti-Evasion": "Anti-Évasion",
    "Group Exemptions": "Exemptions de Groupe",
    "Architecture Overview": "Aperçu de l'Architecture",
    "Testing Guide": "Guide de Test",
    "Basic Enforcement": "Application de Base",
    "Basic Settings": "Paramètres de Base",
    "Core enforcement policies for USB devices": "Politiques d'application de base pour les périphériques USB",
    "Only Enforce on USB Devices": "Appliquer Uniquement aux Périphériques USB",
    "Allow LUKS1 (Read-Only)": "Autoriser LUKS1 (Lecture Seule)",
    "Allow Write with Content Scanning": "Autoriser l'Écriture avec Analyse de Contenu",
    "Desktop Notifications": "Notifications de Bureau",
    "Minimum Passphrase Length": "Longueur Minimale de Phrase Secrète",
    "Exempted Groups": "Groupes Exemptés",
    "Basic": "Base",
    "Security Settings": "Paramètres de Sécurité",
    "Access Control": "Contrôle d'Accès",
    "Secret token and socket security settings": "Paramètres de sécurité des jetons secrets et des sockets",
    "Token TTL (seconds)": "TTL du Jeton (secondes)",
    "Maximum Outstanding Tokens": "Jetons Maximums en Attente",
    "Mount Options": "Options de Montage",
    "Security flags for mounting USB devices": "Drapeaux de sécurité pour le montage de périphériques USB",
    "Plaintext Mount Options": "Options de Montage en Texte Clair",
    "Encrypted Mount Options": "Options de Montage Chiffré",
    "Require No-Execute on Plaintext": "Exiger Non-Exécution sur Texte Clair",
    "Security": "Sécurité",
    "Encryption Settings": "Paramètres de Chiffrement",
    "Encryption Defaults": "Valeurs par Défaut du Chiffrement",
    "Default settings for USB device encryption": "Paramètres par défaut pour le chiffrement de périphériques USB",
    "Default Encryption Type": "Type de Chiffrement par Défaut",
    "Encryption Target": "Cible de Chiffrement",
    "Filesystem Type": "Type de Système de Fichiers",
    "Key Derivation": "Dérivation de Clé",
    "KDF (Key Derivation Function) settings": "Paramètres KDF (Fonction de Dérivation de Clé)",
    "KDF Algorithm": "Algorithme KDF",
    "Cipher Settings": "Paramètres de Chiffrement",
    "Encryption algorithm configuration": "Configuration de l'algorithme de chiffrement",
    "Cipher Algorithm": "Algorithme de Chiffrement",
    "Key Size (bits)": "Taille de Clé (bits)",
    "Encryption": "Chiffrement",
    "Content Scanning (DLP)": "Analyse de Contenu (DLP)",
    "Data Loss Prevention through real-time content scanning": "Prévention de Perte de Données par analyse de contenu en temps réel",
    "Enable Content Scanning": "Activer l'Analyse de Contenu",
    "Scan Encrypted Devices": "Analyser les Périphériques Chiffrés",
    "Action on Detection": "Action lors de la Détection",
    "Scan Categories": "Catégories d'Analyse",
    "Types of sensitive data to detect": "Types de données sensibles à détecter",
    "Enabled Categories": "Catégories Activées",
    "Financial (credit cards, bank accounts, SWIFT, IBAN)": "Financier (cartes de crédit, comptes bancaires, SWIFT, IBAN)",
    "Personal (SSN, passport, driver license, phone)": "Personnel (SSN, passeport, permis de conduire, téléphone)",
    "Authentication (API keys, passwords, tokens)": "Authentification (clés API, mots de passe, jetons)",
    "Medical (medical records, insurance IDs)": "Médical (dossiers médicaux, IDs d'assurance)",
    "Performance Settings": "Paramètres de Performance",
    "Scanning performance and limits": "Performance et limites d'analyse",
    "Max File Size (MB)": "Taille Maximale de Fichier (Mo)",
    "Oversize File Action": "Action Fichier Surdimensionné",
    "Streaming Threshold (MB)": "Seuil de Diffusion (Mo)",
    "Large File Scan Mode": "Mode d'Analyse de Fichiers Volumineux",
    "Scan Timeout (seconds)": "Délai d'Analyse (secondes)",
    "Maximum time to spend scanning a single file.": "Temps maximum pour analyser un seul fichier.",
    "Max Concurrent Scans": "Analyses Concurrentes Maximales",
    "Number of parallel scanning threads.": "Nombre de threads d'analyse parallèles.",
    "Advanced Scanning": "Analyse Avancée",
    "Archive Scanning": "Analyse d'Archives",
    "Scanning files inside archives (ZIP, TAR, 7Z, RAR)": "Analyse de fichiers dans les archives (ZIP, TAR, 7Z, RAR)",
    "Scan Archive Contents": "Analyser le Contenu des Archives",
    "Max Archive Depth": "Profondeur Maximale d'Archive",
    "Document Scanning": "Analyse de Documents",
    "Scanning Office and PDF documents": "Analyse de documents Office et PDF",
    "Scan Documents": "Analyser les Documents",
    "Extract and scan text from PDF, DOCX, XLSX, PPTX, ODT files.": "Extraire et analyser le texte des fichiers PDF, DOCX, XLSX, PPTX, ODT.",
    "Machine Learning": "Apprentissage Automatique",
    "Advanced pattern detection": "Détection avancée de motifs",
    "N-gram Analysis": "Analyse N-gramme",
    "Caching": "Mise en Cache",
    "Scan result caching for performance": "Mise en cache des résultats d'analyse pour la performance",
    "Enable Scan Cache": "Activer le Cache d'Analyse",
    "Cache Size (MB)": "Taille du Cache (Mo)",
    "Maximum size of scan result cache.": "Taille maximale du cache de résultats d'analyse.",
    "Custom Patterns": "Motifs Personnalisés",
    "Define enterprise-specific sensitive data patterns": "Définir des motifs de données sensibles spécifiques à l'entreprise",
    "Manage Custom Patterns": "Gérer les Motifs Personnalisés",
    "{} custom pattern(s) defined": "{} motif(s) personnalisé(s) défini(s)",
    "Advanced": "Avancé",
    "usb-enforcerd restarted.": "usb-enforcerd redémarré.",
    "systemctl not found; cannot restart service.": "systemctl introuvable ; impossible de redémarrer le service.",
    "Failed to restart usb-enforcerd: {}": "Échec du redémarrage d'usb-enforcerd : {}",
    "Custom Content Patterns": "Motifs de Contenu Personnalisés",
    "Add Pattern": "Ajouter un Motif",
    "Name:": "Nom :",
    "e.g., employee_id": "par ex., id_employé",
    "Description:": "Description :",
    "e.g., Company employee ID": "par ex., ID d'employé de l'entreprise",
    "Category:": "Catégorie :",
    "Regex:": "Regex :",
    "e.g., EMP-\\\\d{6}": "par ex., EMP-\\\\d{6}",
    "Test Pattern:": "Tester le Motif :",
    "Test Pattern": "Tester le Motif",
    "Delete Pattern": "Supprimer le Motif",
    "Common Pattern Templates": "Modèles de Motifs Communs",
    "Employee ID": "ID d'Employé",
    "Project Code": "Code de Projet",
    "Account Number": "Numéro de Compte",
    "Internal IP": "IP Interne",
    "Document ID": "ID de Document",
    "Serial Number": "Numéro de Série",
    "Phone (US)": "Téléphone (US)",
    "Email Domain": "Domaine Email",
    "API Key Format": "Format de Clé API",
    "UUID": "UUID",
    "Configuration saved to {}": "Configuration enregistrée dans {}",
    "Configuration saved. Restart usb-enforcerd to apply changes.": "Configuration enregistrée. Redémarrez usb-enforcerd pour appliquer les changements.",
    "Failed to save configuration: {}": "Échec de l'enregistrement de la configuration : {}",
    "Available Documentation": "Documentation Disponible",
    "File Type Support": "Support de Types de Fichiers",
    "Notifications": "Notifications",
    "Main Documentation": "Documentation Principale",
    "Documentation file not found: {}": "Fichier de documentation introuvable : {}",
    "Error loading documentation: {}": "Erreur de chargement de la documentation : {}",
}


def update_po_file(po_file_path, translations, language_name):
    """Update .po file with translations"""
    print(f"\n=== Processing {language_name} translations ===")
    
    with open(po_file_path, 'r', encoding='utf-8') as f:
        content = f.read()
    
    updates = 0
    # Update each translation
    for english, translated in translations.items():
        # Handle both single and multi-line msgid
        # Escape special regex characters but preserve newlines
        escaped_english = english.replace('\\', '\\\\').replace('"', '\\"')
        escaped_translated = translated.replace('\\', '\\\\').replace('"', '\\"')
        
        # Try to find and replace empty msgstr
        # Pattern for single-line msgid
        pattern1 = f'msgid "{re.escape(english)}"\nmsgstr ""'
        replacement1 = f'msgid "{english}"\nmsgstr "{translated}"'
        
        if pattern1 in content:
            content = content.replace(pattern1, replacement1)
            updates += 1
            print(f"  ✓ Translated: {english[:50]}...")
            continue
        
        # Pattern for multi-line msgid (simplified - matches empty msgstr after multi-line msgid)
        lines = content.split('\n')
        i = 0
        while i < len(lines):
            if lines[i].startswith('msgid ') and '"' + english.split('\\n')[0] in lines[i]:
                # Found potential multi-line msgid, look for empty msgstr
                j = i + 1
                while j < len(lines) and not lines[j].startswith('msgstr'):
                    j += 1
                if j < len(lines) and lines[j] == 'msgstr ""':
                    lines[j] = f'msgstr "{translated}"'
                    updates += 1
                    print(f"  ✓ Translated multi-line: {english[:50]}...")
                    break
            i += 1
        
        if i < len(lines):
            content = '\n'.join(lines)
    
    with open(po_file_path, 'w', encoding='utf-8') as f:
        f.write(content)
    
    print(f"\n✓ {updates} translations added to {po_file_path}")
    return updates


if __name__ == "__main__":
    # Update Spanish
    es_updates = update_po_file(
        "locale/es/LC_MESSAGES/usb-enforcer.po",
        spanish_translations,
        "Spanish"
    )
    
    # Update French
    fr_updates = update_po_file(
        "locale/fr/LC_MESSAGES/usb-enforcer.po",
        french_translations,
        "French"
    )
    
    print(f"\n=== Summary ===")
    print(f"Spanish: {es_updates} translations added")
    print(f"French: {fr_updates} translations added")
    print("\nNext steps:")
    print("1. Compile Spanish: msgfmt locale/es/LC_MESSAGES/usb-enforcer.po -o locale/es/LC_MESSAGES/usb-enforcer.mo")
    print("2. Compile French: msgfmt locale/fr/LC_MESSAGES/usb-enforcer.po -o locale/fr/LC_MESSAGES/usb-enforcer.mo")
    print("3. Test with: LANGUAGE=es python3 src/usb_enforcer/ui/admin.py")
