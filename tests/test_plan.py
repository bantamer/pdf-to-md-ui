"""Where each PDF's results go: plan_jobs()."""

import os
from pathlib import Path

from converter import plan_jobs


def touch(path: Path) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"%PDF-1.4\n")
    return path


def targets(jobs, root):
    """{label: output dir relative to root} - easy to read in an assert."""
    return {
        j.label: Path(j.output_dir).relative_to(root).as_posix() for j in jobs
    }


def test_same_name_in_two_folders_does_not_overwrite(tmp_path):
    """The bug: a/doc.pdf and b/doc.pdf both became <root>/doc.md."""
    a = touch(tmp_path / "a" / "doc.pdf")
    b = touch(tmp_path / "b" / "doc.pdf")
    root = tmp_path / "out"

    jobs = plan_jobs([str(a), str(b)], str(root))

    dirs = {os.path.normcase(j.output_dir) for j in jobs}
    assert len(jobs) == 2
    assert len(dirs) == 2, "both files would write doc.md into the same folder"


def test_hand_picked_files_with_one_name_get_numbered_folder(tmp_path):
    a = touch(tmp_path / "a" / "doc.pdf")
    b = touch(tmp_path / "b" / "doc.pdf")
    root = tmp_path / "out"

    jobs = plan_jobs([str(a), str(b)], str(root))

    assert Path(jobs[0].output_dir) == root
    assert Path(jobs[1].output_dir) == root / "doc (2)"
    # The bare name no longer tells them apart, so the label is the full path.
    assert {j.label for j in jobs} == {str(a), str(b)}


def test_single_folder_keeps_its_structure_without_extra_level(tmp_path):
    src = tmp_path / "datasheets"
    touch(src / "top.pdf")
    touch(src / "TI" / "tps7a02.pdf")
    touch(src / "ADI" / "deep" / "adp150.pdf")
    root = tmp_path / "out"

    jobs = plan_jobs([str(src)], str(root))

    assert targets(jobs, root) == {
        "top.pdf": ".",
        "TI/tps7a02.pdf": "TI",
        "ADI/deep/adp150.pdf": "ADI/deep",
    }


def test_several_folders_each_get_their_own_subfolder(tmp_path):
    touch(tmp_path / "TI" / "doc.pdf")
    touch(tmp_path / "ADI" / "doc.pdf")
    root = tmp_path / "out"

    jobs = plan_jobs([str(tmp_path / "TI"), str(tmp_path / "ADI")], str(root))

    assert targets(jobs, root) == {"TI/doc.pdf": "TI", "ADI/doc.pdf": "ADI"}


def test_results_folder_inside_the_source_is_skipped(tmp_path):
    """Default destination is <folder>/output - its PDFs are not new input."""
    src = tmp_path / "src"
    touch(src / "doc.pdf")
    touch(src / "output" / "doc_annotated.pdf")
    touch(src / "output" / "old" / "whatever.pdf")

    jobs = plan_jobs([str(src)], str(src / "output"))

    assert [j.label for j in jobs] == ["doc.pdf"]


def test_results_written_next_to_sources_are_not_reconverted(tmp_path):
    """Destination == source folder: doc_annotated.pdf sits beside doc.pdf."""
    src = tmp_path / "src"
    touch(src / "doc.pdf")
    touch(src / "doc_annotated.pdf")
    touch(src / "doc_tagged.pdf")

    jobs = plan_jobs([str(src)], str(src))

    assert [j.label for j in jobs] == ["doc.pdf"]


def test_annotated_name_without_original_is_a_real_input(tmp_path):
    """Only a derived file next to its original is skipped, not the name alone."""
    src = tmp_path / "src"
    touch(src / "report_annotated.pdf")

    jobs = plan_jobs([str(src)], str(tmp_path / "out"))

    assert [j.label for j in jobs] == ["report_annotated.pdf"]


def test_hand_picked_derived_file_is_still_converted(tmp_path):
    """Picking a file by hand is an explicit request, whatever its name."""
    touch(tmp_path / "doc.pdf")
    derived = touch(tmp_path / "doc_annotated.pdf")

    jobs = plan_jobs([str(derived)], str(tmp_path / "out"))

    assert len(jobs) == 1


def test_file_and_its_folder_selected_together_converts_once(tmp_path):
    src = tmp_path / "src"
    doc = touch(src / "doc.pdf")

    jobs = plan_jobs([str(src), str(doc)], str(tmp_path / "out"))

    assert len(jobs) == 1


def test_non_pdf_and_missing_paths_are_ignored(tmp_path):
    src = tmp_path / "src"
    touch(src / "doc.pdf")
    (src / "notes.txt").write_text("x")

    jobs = plan_jobs([str(src), str(tmp_path / "gone.pdf")], str(tmp_path / "out"))

    assert [j.label for j in jobs] == ["doc.pdf"]


def test_pdf_extension_in_any_case(tmp_path):
    src = tmp_path / "src"
    touch(src / "LOUD.PDF")

    assert len(plan_jobs([str(src)], str(tmp_path / "out"))) == 1
