import facere as fac


@fac.rule(default=True)
def greet(program: fac.Input = "tools/greet", target: fac.Output = fac.out("greeting.txt")):
    greeting = fac.run(program, cwd="sub", quiet=True)
    with open(target, "w") as file:
        file.write(greeting)
