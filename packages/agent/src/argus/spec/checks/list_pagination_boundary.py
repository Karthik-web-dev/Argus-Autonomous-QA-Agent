from .common import define_check

CHECK = define_check(
    id="list-pagination-boundary",
    title="Pagination boundaries",
    category="lists",
    family="any",
    action="assert_pagination_boundaries",
    value=None,
    expected="The first and last pages expose correct previous and next states.",
)

