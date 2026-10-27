from .common import define_check

CHECK = define_check(
    id="form-preserve-valid-input",
    title="Preserve input after validation error",
    category="forms",
    family="form",
    action="fill",
    value="valid draft value",
    expected="Valid fields retain their values when another field fails validation.",
)

