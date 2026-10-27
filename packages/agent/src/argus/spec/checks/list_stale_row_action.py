from .common import define_check

CHECK = define_check(
    id="list-stale-row-action",
    title="Action on stale list item",
    category="lists",
    family="list",
    action="click",
    value=None,
    expected="An action on an item removed since loading fails safely and refreshes state.",
)

