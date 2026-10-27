from .common import define_check

CHECK = define_check(
    id="list-large-page",
    title="Large result page",
    category="lists",
    family="list",
    action="click",
    value=None,
    expected="A large result page remains responsive and renders the correct item count.",
)

