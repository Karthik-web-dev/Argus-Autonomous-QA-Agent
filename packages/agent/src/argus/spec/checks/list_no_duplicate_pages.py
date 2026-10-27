from .common import define_check

CHECK = define_check(
    id="list-no-duplicate-pages",
    title="Duplicate entries across pages",
    category="lists",
    family="list",
    action="click",
    value=None,
    expected="Paginated results do not repeat the same item across adjacent pages.",
)

