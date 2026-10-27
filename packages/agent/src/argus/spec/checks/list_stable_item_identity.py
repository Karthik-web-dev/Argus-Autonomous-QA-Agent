from .common import define_check

CHECK = define_check(
    id="list-stable-item-identity",
    title="Stable identity after sorting",
    category="lists",
    family="list",
    action="click",
    value=None,
    expected="Sorting preserves item identity and does not attach actions to another row.",
)

