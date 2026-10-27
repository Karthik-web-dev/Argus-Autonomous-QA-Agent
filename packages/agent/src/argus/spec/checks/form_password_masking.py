from .common import define_check

CHECK = define_check(
    id="form-password-masking",
    title="Password field privacy",
    category="forms",
    family="password",
    action="fill",
    value="Argus-test-password",
    expected="Password fields remain masked and are not exposed in rendered text.",
    flow="password",
)

