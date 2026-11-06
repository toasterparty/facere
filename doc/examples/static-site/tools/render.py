"""A small Markdown subset rendered to HTML: a `# title` line, then paragraphs split by blank lines."""


def find_title(markdown):
    return markdown.splitlines()[0].removeprefix("# ")


def render_body(markdown):
    title, *paragraphs = markdown.split("\n\n")
    html = [f"<h1>{find_title(title)}</h1>"]
    html += [f"<p>{paragraph.strip()}</p>" for paragraph in paragraphs]
    return "\n".join(html)


def fill_template(template, site, title, body):
    return template.format(site=site, title=title, body=body)
