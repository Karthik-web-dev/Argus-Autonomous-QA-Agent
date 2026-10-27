from .common import define_check

CHECK = define_check(
    id="list-keyboard-navigation",
    title="Keyboard list navigation",
    category="lists",
    family="list",
    action="click",
    value=None,
    expected="List controls remain operable with keyboard focus and activation.",
)

