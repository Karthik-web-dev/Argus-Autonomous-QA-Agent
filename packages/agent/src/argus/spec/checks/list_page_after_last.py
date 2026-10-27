from .common import define_check

CHECK = define_check(
    id="list-page-after-last",
    title="Page beyond final result",
    category="lists",
    family="list",
    action="click",
    value=None,
    expected="The application never exposes an invalid page beyond the final result.",
)

