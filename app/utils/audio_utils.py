"""
LionFlow AI — Utilitaires audio.
Conversion vers OGG/OPUS (format obligatoire pour les notes vocales WhatsApp).
"""

from __future__ import annotations

import os
import shutil
import subprocess
from typing import Optional


class AudioConversionError(Exception):
    """Erreur lors de la conversion audio."""


def _ffmpeg_available() -> bool:
    return shutil.which("ffmpeg") is not None


def convert_to_ogg_opus(
    input_path: str,
    output_path: Optional[str] = None,
    bitrate: str = "32k",
    mono: bool = True,
) -> str:
    """
    Convertit un fichier audio (mp3, wav, webm, m4a…) en OGG/OPUS.

    Retourne le chemin du fichier de sortie.
    Lève AudioConversionError si ffmpeg n'est pas installé ou si la conversion échoue.
    """
    if not os.path.isfile(input_path):
        raise AudioConversionError(f"Fichier source introuvable : {input_path}")

    if output_path is None:
        base, _ = os.path.splitext(input_path)
        output_path = f"{base}.opus.ogg"

    if not _ffmpeg_available():
        raise AudioConversionError(
            "ffmpeg introuvable. Installez-le : winget install ffmpeg (Windows) "
            "ou apt install ffmpeg (Linux)."
        )

    cmd = [
        "ffmpeg",
        "-y",
        "-i", input_path,
        "-vn",
        "-map_metadata", "-1",
        "-ac", "1" if mono else "2",
        "-ar", "48000",
        "-c:a", "libopus",
        "-b:a", bitrate,
        "-f", "ogg",
        output_path,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
        )
    except subprocess.TimeoutExpired:
        raise AudioConversionError("Conversion audio : délai dépassé (60s)")

    if result.returncode != 0:
        raise AudioConversionError(
            f"Conversion ffmpeg échouée (code {result.returncode}): "
            f"{result.stderr[-500:]}"
        )

    if not os.path.isfile(output_path) or os.path.getsize(output_path) == 0:
        raise AudioConversionError("Fichier OPUS généré vide ou absent")

    return output_path


def get_audio_duration_seconds(file_path: str) -> float:
    """Retourne la durée d'un fichier audio en secondes (via ffprobe)."""
    if not _ffmpeg_available():
        return 0.0
    try:
        result = subprocess.run(
            [
                "ffprobe",
                "-v", "error",
                "-show_entries", "format=duration",
                "-of", "default=noprint_wrappers=1:nokey=1",
                file_path,
            ],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return float(result.stdout.strip()) if result.stdout.strip() else 0.0
    except (ValueError, subprocess.SubprocessError):
        return 0.0