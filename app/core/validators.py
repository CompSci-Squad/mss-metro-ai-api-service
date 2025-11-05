"""
Validadores para o VIRAG-BIM.
Contém funções auxiliares para validação de dados.
"""

import re
from pathlib import Path

from fastapi import HTTPException, UploadFile, status
from ulid import ULID


def validate_ulid(ulid_str: str) -> str:
    """
    Valida formato ULID.

    Args:
        ulid_str: String para validar

    Returns:
        String ULID validada

    Raises:
        HTTPException: Se ULID for inválido
    """
    try:
        ULID.from_str(ulid_str)
        return ulid_str
    except (ValueError, AttributeError) as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"ULID inválido: {ulid_str}",
        ) from e


def validate_file_extension(filename: str, allowed_extensions: list[str]) -> str:
    """
    Valida extensão de arquivo.

    Args:
        filename: Nome do arquivo
        allowed_extensions: Lista de extensões permitidas (ex: ['.jpg', '.png'])

    Returns:
        Nome do arquivo validado

    Raises:
        HTTPException: Se extensão não for permitida
    """
    if not filename:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nome de arquivo inválido",
        )

    file_ext = Path(filename).suffix.lower()
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Formato não suportado. Use: {', '.join(allowed_extensions)}",
        )

    return filename


async def validate_file_size(file: UploadFile, max_size_mb: int) -> bytes:
    """
    Valida tamanho do arquivo.

    Args:
        file: Arquivo upload
        max_size_mb: Tamanho máximo em MB

    Returns:
        Conteúdo do arquivo em bytes

    Raises:
        HTTPException: Se arquivo exceder tamanho máximo
    """
    content = await file.read()
    size_mb = len(content) / (1024 * 1024)

    if size_mb > max_size_mb:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"Arquivo muito grande: {size_mb:.2f}MB. Máximo: {max_size_mb}MB",
        )

    return content


def sanitize_filename(filename: str) -> str:
    """
    Remove caracteres perigosos de nome de arquivo.

    Args:
        filename: Nome do arquivo original

    Returns:
        Nome sanitizado
    """
    # Remove path traversal
    filename = Path(filename).name

    # Remove caracteres não-ASCII e especiais
    filename = re.sub(r"[^\w\s.-]", "", filename)

    # Limita tamanho
    if len(filename) > 255:
        name, ext = Path(filename).stem, Path(filename).suffix
        filename = name[:250] + ext

    return filename


def validate_project_name(name: str) -> str:
    """
    Valida nome de projeto.

    Args:
        name: Nome do projeto

    Returns:
        Nome validado

    Raises:
        HTTPException: Se nome for inválido
    """
    if not name or len(name.strip()) < 3:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nome do projeto deve ter pelo menos 3 caracteres",
        )

    if len(name) > 200:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Nome do projeto não pode exceder 200 caracteres",
        )

    return name.strip()
