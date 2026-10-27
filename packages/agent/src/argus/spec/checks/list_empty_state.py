from .common import define_check

CHECK = define_check(
    id="list-empty-state",
    title="Empty list state",
    category="lists",
    family="form",
    action="fill",
    value="argus-empty-state-probe-71c",
    expected="An empty list explains that no records are available.",
    flow="filter_zero",
)

