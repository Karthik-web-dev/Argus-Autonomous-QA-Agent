from .common import define_check

CHECK = define_check(
    id="list-whitespace-filter",
    title="Whitespace-only filter",
    category="lists",
    family="form",
    action="fill",
    value="   ",
    expected="Whitespace filters are normalized and do not cause unexpected results.",
    flow="whitespace_filter",
)

