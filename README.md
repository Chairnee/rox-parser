# Rox Parser

A tool to parse Ivanti .rox files and produce request offering and workflow visualisations.

The tool is in an early stage and has known shortcomings. The two most significant at this time are:

1. It is currently biased to the developer's use case and isn't customisable. For example, the tool does not include field translations in the parameter table output because it is irrelevant in the developer's environment.

2. The logic behind the generation of the directed graph for request offering parameters is rudimentary at this time. It simply checks whether the ID of a parameter, such as "Employee", exists in the logical expressions of other parameters. Depending on how unique the ID of a given parameter is, it could overlap with the name of other system objects and cause false positive dependency relationships. For instance, consider this scenario: field A has the ID "Employee" and field B has a visibility expression containing a reference to the Employee# record table like "Employee.xyz". Under the current implementation, Field B will be considered a logically dependent child of field A regardless of whether that is true or not. This will be resolved later.

## Optional External Dependency Notice

Generating DOT graph svgs for parameters requires the Graphviz binary to be installed and accessible through PATH. Svg generation will be skipped and a warning presented if it is not installed.

## General Use

The tool can be used from command line.

```powershell
rox-parser "rox file path" --export-default-set
```

There is one argument intended for general use, which is : --export-default-set

This will output a graph.svg, param_report.html and workflow_report.html to the current directory.

See rox-parser -h for all arguments and a brief description. Most arguments print to standard output, so they can be redirected:

```powershell
rox-parser "file_name.rox" --param-json > output.json
```
