from .common import define_check

CHECK = define_check(
    id="list-refresh",
    title="Refresh list state",
    category="lists",
    family="list",
    action="click",
    value=None,
    expected="Reloading the list returns consistent data and selection state.",
)

