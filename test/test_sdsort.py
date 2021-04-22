# TODO: parametrize once there are multiple test cases
# TODO: add test cases for
# - preservation of comments/docstrings
# - nested classes?
# - nested functions
# - circular references
from sdsort import step_down_sort


def test_all_cases():
    # Arrange
    input_file_path = "test/cases/single_class.in.py"
    expected_output_file_path = "test/cases/single_class.out.py"
    #in_text = read_file(input_file_path)
    expected_output = read_file(expected_output_file_path)

    # Act
    actual_output = step_down_sort(input_file_path)

    assert actual_output == expected_output


def read_file(path: str) -> str:
    with open(path) as file:
        return file.read()
