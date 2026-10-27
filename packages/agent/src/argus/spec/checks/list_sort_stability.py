from .common import define_check

CHECK = define_check(
    id="list-sort-stability",
    title="Sort stability",
    category="lists",
    family="list",
    action="assert_sort_stability",
    value=None,
    expected="Equal sort keys retain a stable order across repeated sorting.",
    flow="sort_stability",
)

