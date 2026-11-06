import facere as fac


@fac.rule(default=True)
def greet(target: fac.Output = fac.out("greeting.txt")):
    greeting = fac.run("tools/greet", cwd="sub", quiet=True)
    with open(target, "w") as file:
        file.write(greeting)
