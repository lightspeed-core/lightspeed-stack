# Dynamic dispatch: functional style


@singledispatch
def function(arg: Any) -> None:
    print("Original function with argument", arg, "that has type", type(arg))


@function.register
def _(arg: int | str) -> None:
    print("Integer variant with int or str argument:", arg)


@function.register(list | tuple)
def _(arg: list[Any] | tuple[Any, ...]) -> None:
    print("List or tuple variant with argument:", arg)


@function.register
def _(arg: None) -> None:
    print("None variant with argument:", arg)


function(42)
function("foo")
function(["foo", "bar", "baz"])
function(("foo", "bar", "baz"))
function(1.4142)
function(None)
