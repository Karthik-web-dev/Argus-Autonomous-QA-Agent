from .common import define_check

CHECK = define_check(
    id="list-zero-result-filter",
    title="Zero-result filter",
    category="lists",
    family="form",
    action="fill",
    value="argus-no-match-7f3",
    expected="A filter with no matches shows a useful empty state.",
    flow="filter_zero",
)

