from .common import define_check

CHECK = define_check(
    id="form-keyboard-submit",
    title="Keyboard-only form submission",
    category="forms",
    family="form",
    action="fill",
    value="Argus keyboard test input",
    expected="The form can be completed and submitted using the keyboard alone.",
    flow="keyboard",
)

