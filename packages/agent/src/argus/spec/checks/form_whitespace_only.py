from .common import define_check

CHECK = define_check(
    id="form-whitespace-only",
    title="Whitespace-only input",
    category="forms",
    family="form",
    action="fill",
    value="   \t  ",
    expected="Whitespace-only values are normalized or rejected consistently.",
)

