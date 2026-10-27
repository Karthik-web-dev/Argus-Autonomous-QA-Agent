from .common import define_check

CHECK = define_check(
    id="list-filter-resets-page",
    title="Filter resets pagination",
    category="lists",
    family="form",
    action="fill",
    value="argus",
    expected="Changing a filter resets to a valid page.",
)

