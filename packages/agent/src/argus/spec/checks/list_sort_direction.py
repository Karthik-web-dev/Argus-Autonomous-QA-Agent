from .common import define_check

CHECK = define_check(
    id="list-sort-direction",
    title="Sort direction toggle",
    category="lists",
    family="list",
    action="click",
    value=None,
    expected="Repeated sort activation toggles direction predictably.",
)

