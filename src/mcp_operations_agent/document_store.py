from pathlib import Path

from mcp_operations_agent.models import (
    DocumentContent,
    DocumentMetadata,
    DocumentSearchMatch,
)


DEFAULT_ALLOWED_EXTENSIONS = frozenset(
    {
        ".csv",
        ".json",
        ".md",
        ".txt",
    }
)


class DocumentStore:
    """Read-only access to an approved document root."""

    def __init__(
        self,
        root: str | Path,
        *,
        maximum_file_bytes: int = 100_000,
        allowed_extensions: frozenset[str] = (
            DEFAULT_ALLOWED_EXTENSIONS
        ),
    ) -> None:
        if maximum_file_bytes <= 0:
            raise ValueError(
                "maximum_file_bytes must be "
                "greater than zero"
            )

        if not allowed_extensions:
            raise ValueError(
                "allowed_extensions cannot be empty"
            )

        self.root = Path(root).resolve()
        self.maximum_file_bytes = (
            maximum_file_bytes
        )
        self.allowed_extensions = frozenset(
            extension.lower()
            for extension in allowed_extensions
        )

    def initialize(self) -> None:
        """Create the approved root when missing."""

        self.root.mkdir(
            parents=True,
            exist_ok=True,
        )

        if not self.root.is_dir():
            raise RuntimeError(
                "Document root is not a directory: "
                f"{self.root}"
            )

    def list_documents(
        self,
        *,
        relative_directory: str = ".",
        limit: int = 100,
    ) -> list[DocumentMetadata]:
        if not 1 <= limit <= 100:
            raise ValueError(
                "limit must be between 1 and 100"
            )

        directory = self._resolve_path(
            relative_directory
        )

        if not directory.exists():
            raise FileNotFoundError(
                "Document directory was not found"
            )

        if not directory.is_dir():
            raise ValueError(
                "Document path is not a directory"
            )

        documents: list[DocumentMetadata] = []

        for path in sorted(directory.rglob("*")):
            if not path.is_file():
                continue

            if not self._is_allowed_extension(path):
                continue

            resolved_path = path.resolve()

            if not self._is_within_root(resolved_path):
                continue

            documents.append(
                DocumentMetadata(
                    relative_path=(
                        resolved_path
                        .relative_to(self.root)
                        .as_posix()
                    ),
                    size_bytes=(
                        resolved_path.stat().st_size
                    ),
                )
            )

            if len(documents) >= limit:
                break

        return documents

    def read_document(
        self,
        relative_path: str,
    ) -> DocumentContent:
        path = self._resolve_path(relative_path)

        if not path.exists():
            raise FileNotFoundError(
                "Document was not found"
            )

        if not path.is_file():
            raise ValueError(
                "Document path is not a file"
            )

        self._require_allowed_extension(path)
        self._require_allowed_size(path)

        try:
            content = path.read_text(
                encoding="utf-8"
            )
        except UnicodeDecodeError as error:
            raise ValueError(
                "Document must contain valid UTF-8 text"
            ) from error
        except OSError as error:
            raise RuntimeError(
                "Could not read document"
            ) from error

        return DocumentContent(
            relative_path=(
                path.relative_to(self.root).as_posix()
            ),
            content=content,
        )

    def search_documents(
        self,
        query: str,
        *,
        limit: int = 20,
    ) -> list[DocumentSearchMatch]:
        normalized_query = query.strip().casefold()

        if len(normalized_query) < 2:
            raise ValueError(
                "query must contain at least "
                "two characters"
            )

        if not 1 <= limit <= 50:
            raise ValueError(
                "limit must be between 1 and 50"
            )

        matches: list[DocumentSearchMatch] = []

        for document in self.list_documents(
            limit=100
        ):
            if document.size_bytes > (
                self.maximum_file_bytes
            ):
                continue

            try:
                content = self.read_document(
                    document.relative_path
                )
            except (
                FileNotFoundError,
                RuntimeError,
                ValueError,
            ):
                continue

            for line_number, line in enumerate(
                content.content.splitlines(),
                start=1,
            ):
                normalized_line = line.casefold()

                if normalized_query not in normalized_line:
                    continue

                excerpt = line.strip()

                if not excerpt:
                    continue

                matches.append(
                    DocumentSearchMatch(
                        relative_path=(
                            document.relative_path
                        ),
                        line_number=line_number,
                        excerpt=excerpt[:500],
                    )
                )

                if len(matches) >= limit:
                    return matches

        return matches

    def _resolve_path(
        self,
        relative_path: str,
    ) -> Path:
        normalized_path = relative_path.strip()

        if not normalized_path:
            raise ValueError(
                "relative_path cannot be empty"
            )

        supplied_path = Path(normalized_path)

        if supplied_path.is_absolute():
            raise ValueError(
                "Absolute paths are not allowed"
            )

        resolved_path = (
            self.root / supplied_path
        ).resolve()

        if not self._is_within_root(resolved_path):
            raise ValueError(
                "Path escapes the approved "
                "document root"
            )

        return resolved_path

    def _is_within_root(
        self,
        path: Path,
    ) -> bool:
        try:
            path.relative_to(self.root)
        except ValueError:
            return False

        return True

    def _is_allowed_extension(
        self,
        path: Path,
    ) -> bool:
        return (
            path.suffix.lower()
            in self.allowed_extensions
        )

    def _require_allowed_extension(
        self,
        path: Path,
    ) -> None:
        if not self._is_allowed_extension(path):
            raise ValueError(
                "Document extension is not allowed"
            )

    def _require_allowed_size(
        self,
        path: Path,
    ) -> None:
        if path.stat().st_size > (
            self.maximum_file_bytes
        ):
            raise ValueError(
                "Document exceeds the maximum "
                "allowed size"
            )