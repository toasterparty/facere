import facere as fac


class Pages:
    def __init__(self, url):
        self.url = url

    def stamp(self):
        return None

    def read(self, keys):
        return {}

    def update(self, changed):
        pass


CMS = Pages("https://cms.example.com/pages")


@fac.rule(output="build/a.txt")
def text_as_virtual(output: fac.Output[fac.Virtual]):
    pass


@fac.rule(source=fac.Virtual("about", store=CMS))
def virtual_as_path(source: fac.Input, output: fac.Output = "build/b.txt"):
    pass


@fac.rule
def uri(source: fac.Input = "s3://sales/2026.csv", output: fac.Output = "build/c.txt"):
    pass


@fac.rule(output=fac.Virtual("v1", fingerprint=len))
def signed(output: fac.Output[fac.Virtual]):
    pass


@fac.task(pages=[fac.Virtual("about", store=CMS)])
def publish(pages: list[fac.Input[fac.Virtual]]):
    pass
