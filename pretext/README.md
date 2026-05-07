# PreTeXt Book Version

This directory contains the PreTeXt version of *Learning Statistics with R*.

## Building the Book

To build the book locally:

```bash
cd pretext
pretext build web
```

To view the built book:

```bash
pretext view web
```

## GitHub Actions Deployment

The book is automatically built and validated when commits are made to pull requests, and deployed to GitHub Pages when changes are pushed to the main branch. See `.github/workflows/deploy-pretext.yml` for the deployment configuration.

## R Code Support

The book includes support for R code examples with syntax highlighting. R code blocks are defined using:

```xml
<program language="r">
  <input>
# Your R code here
x &lt;- 10  # Use &lt; for < in XML
  </input>
</program>
```

For interactive code blocks, add the `interactive="yes"` attribute.

## Images

Images should be placed in the `source/images/` directory or the `assets/` directory and can be included using the `<image>` element in PreTeXt.

## Project Structure

- `source/` - PreTeXt source files (.ptx)
- `source/main.ptx` - Main book file
- `source/ch_*.ptx` - Chapter files
- `source/images/` - Image source files
- `assets/` - Static assets (images, data files, etc.)
- `publication/` - Publication configuration
- `project.ptx` - Project configuration
- `output/` - Generated output (not tracked in git)

## More Information

For more information about PreTeXt, visit:
- PreTeXt documentation: https://pretextbook.org/
- PreTeXt Guide: https://pretextbook.org/doc/guide/html/
