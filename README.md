`excimer_referencer` is a tool to convert and spatially reference .png, .bmp, and .jpg files produced from a laser ablation system into geotiffs that can be imported into QGIS.

It can be installed from pypi with `pip install excimer_referencer`.

The tool depends on some dependencies that are difficult to install with pip alone (GDAL). On some machines, `pip install excimer_referencer` might work if GDAL is already installed and configured in a certain way.
But if this doesn't work right away, it's best to set up a silo-ed programming enviornment specifically for the referencer tool.

After cloning/downloading this repository, set up the environment with the following:
1. Make sure that you have Anaconda python 3.7 installed for your operating system. See: https://www.anaconda.com/distribution/
2. Open the Anaconda prompt. Navigate to the excimer_referencer folder you downloaded using the `cd` command in the Anaconda prompt. Use `dir` to figure out which folder you are in inside the prompt.
3. Run these commands to setup the environment, install the package, and activate the environment: 

```
conda env create -f environment.yml
conda activate referencer
flit install --symlink --python $(which python) 
# flit is a tool for quickly publishing python packages for the world, but we use it here to do a development install
# if you edit the refgerencer code, those changes will appear when you try to run the referencer command line tool.
```

Whenever you need to use the excimer_referencer tool, you will need to run `conda activate referencer` first.

Finally, run `referencer --help` in the prompt to get a help page for the tool.

```
NAME
    referencer - This spatially references all images in a folder and saves .tifs to another folder.

SYNOPSIS
    referencer INFOLDER OUTFOLDER <flags>

DESCRIPTION
    A wildcard pattern is used to match each image (.bmp, .png. or .jpeg) to a 
    corresponding align file. Each image's align file must have the same unique 
    identifiers.
    For example: W235 9 51 191028195737 together form unique ids in the filename
    ScanImage_W235_9_51_Ablation_EndPattern_191028195737.png
    Align files must be in xml and must follow schemas supported by this script.

POSITIONAL ARGUMENTS
    INFOLDER
    OUTFOLDER

FLAGS
    --img_path_pattern=IMG_PATH_PATTERN
    --align_path_pattern=ALIGN_PATH_PATTERN

NOTES
    You can also use flags syntax for POSITIONAL ARGUMENTS

``` 
