import os
from os import path

from app.helpers.supporting_files import uniquify


def test_uniquify_returns_unused_path_unchanged(test_settings):
    unused_path = "foo.txt"

    assert uniquify(test_settings, unused_path) == unused_path


def test_uniquify_changes_used_path(test_settings):
    temp_file_storage_path = test_settings.temp_file_storage_path
    used_path = "foo.csv"
    with open(path.join(temp_file_storage_path, used_path), "w") as f: f.write("")

    assert uniquify(test_settings, used_path) == "foo(1).csv"


def test_uniquify_tries_multiple_paths(test_settings):
    temp_file_storage_path = test_settings.temp_file_storage_path
    used_path = "foo.csv"
    used_path_1 = "foo(1).csv"
    used_path_2 = "foo(2).csv"
    with open(path.join(temp_file_storage_path, used_path), "w") as f: f.write("")
    with open(path.join(temp_file_storage_path, used_path_1), "w") as f: f.write("")
    with open(path.join(temp_file_storage_path, used_path_2), "w") as f: f.write("")

    assert uniquify(test_settings, used_path) == "foo(3).csv"


def test_uniquify_changes_used_path_in_directory(test_settings):
    temp_file_storage_path = test_settings.temp_file_storage_path
    used_path = path.join("some_dir", "another_dir", "foo.csv")
    os.makedirs(path.join(temp_file_storage_path, "some_dir", "another_dir"), exist_ok=True)
    with open(path.join(temp_file_storage_path, used_path), "w") as f: f.write("")

    assert uniquify(test_settings, used_path) == path.join("some_dir", "another_dir", "foo(1).csv")
