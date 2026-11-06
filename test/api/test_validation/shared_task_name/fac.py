import facere as fac


def greet(word="hello"):
    print(word)


fac.task(name="greet", word="hi")(greet)
fac.task(name="greet", word="hey")(greet)
