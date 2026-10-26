from pathlib import Path

import pytest

from mcp_operations_agent.document_store import (
    DocumentStore,
)


@pytest.fixture
def document_store(
    tmp_path: Path,
) -> DocumentStore:
    root = tmp_path / "knowledge"
    root.mkdir()

    (root / "operations.md").write_text(
        (
            "# Operations\n\n"
            "Pending orders must be reviewed "
            "within one business day.\n"
        ),
        encoding="utf-8",
    )

    (root / "customers.txt").write_text(
        (
            "Inactive customers must not receive "
            "new orders.\n"
        ),
        encoding="utf-8",
    )

    (root / "ignored.exe").write_text(
        "This file must not be exposed.",
        encoding="utf-8",
    )

    return DocumentStore(root)


def test_store_lists_allowed_documents(
    document_store: DocumentStore,
) -> None:
    documents = (
        document_store.list_documents()
    )

    assert [
        document.relative_path
        for document in documents
    ] == [
        "customers.txt",
        "operations.md",
    ]


def test_store_reads_document(
    document_store: DocumentStore,
) -> None:
    document = document_store.read_document(
        "operations.md"
    )

    assert document.relative_path == (
        "operations.md"
    )
    assert "Pending orders" in document.content


def test_store_searches_documents(
    document_store: DocumentStore,
) -> None:
    matches = (
        document_store.search_documents(
            "pending orders"
        )
    )

    assert len(matches) == 1
    assert matches[0].relative_path == (
        "operations.md"
    )
    assert matches[0].line_number == 3


def test_store_rejects_path_traversal(
    document_store: DocumentStore,
) -> None:
    with pytest.raises(
        ValueError,
        match="escapes",
    ):
        document_store.read_document(
            "../secret.txt"
        )


def test_store_rejects_absolute_path(
    document_store: DocumentStore,
    tmp_path: Path,
) -> None:
    outside_file = tmp_path / "secret.txt"
    outside_file.write_text(
        "Secret",
        encoding="utf-8",
    )

    with pytest.raises(
        ValueError,
        match="Absolute paths",
    ):
        document_store.read_document(
            str(outside_file.resolve())
        )


def test_store_rejects_disallowed_extension(
    document_store: DocumentStore,
) -> None:
    with pytest.raises(
        ValueError,
        match="extension",
    ):
        document_store.read_document(
            "ignored.exe"
        )


def test_store_rejects_oversized_document(
    tmp_path: Path,
) -> None:
    root = tmp_path / "knowledge"
    root.mkdir()

    (root / "large.txt").write_text(
        "A" * 11,
        encoding="utf-8",
    )

    store = DocumentStore(
        root,
        maximum_file_bytes=10,
    )

    with pytest.raises(
        ValueError,
        match="maximum allowed size",
    ):
        store.read_document("large.txt")


def test_store_rejects_invalid_search_query(
    document_store: DocumentStore,
) -> None:
    with pytest.raises(
        ValueError,
        match="at least two characters",
    ):
        document_store.search_documents(" ")