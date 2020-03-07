import pandas as pd
import skimage.io as skio
from pathlib import Path
import xml.etree.ElementTree as et 
import numpy as np
import affine
import os
from osgeo import gdal, osr
import fire
import re

def check_int(s):
    """Sourced from helpful post from SO 
    https://stackoverflow.com/questions/1265665/how-can-i-check-if-a-string-represents-an-int-without-using-try-except"""
    if s[0] in ('-', '+'):
        return s[1:].isdigit()
    return s.isdigit()

def match_img_align(img_file_path, align_file_path):
    """Tests if img and align file IDs are the same. This is an old function that only works for one filenaming schema.s"""
    img_name = str(img_file_path.name)
    align_name = str(align_file_path.name)
    accepted_formats = ["tif", "bmp", "png", "Align", "align", "jpeg", "jpg"]
    if (img_name.split(".")[-1] not in accepted_formats) or (align_name.split(".")[-1] not in accepted_formats):
        raise ValueError(f"one of {img_name} or {align_name} doe snot have an accepted format: {accepted_formats}")
    # handles case for CRS image
    if (img_name.startswith("Image") and align_name.startswith("Image")) or \
    (img_name.startswith("Mosaic") and align_name.startswith("Mosaic")):
        if img_name.split(".")[0] == align_name.split(".")[0]:
            return (img_file_path, align_file_path)
    # handles case for smaller scan images
    else:
        # gets text between these two strings sicne they can be of variable length 
        # and with different delimiting characters
        if img_name.startswith("Image") or align_name.startswith("Image") or \
           img_name.startswith("Mosaic") or align_name.startswith("Mosaic"):
            pass
        else:
            imgid1 = re.search('ScanImage(.*)EndPattern', img_name).group(1)
            alignid1 = re.search('ScanImage(.*)EndPattern', align_name).group(1)
            imgid2 = img_name.split("_")[-1][:-4]
            alignid2 = align_name.split("_")[-1][:-6]
            if imgid1 == alignid1 and imgid1 == alignid1:
                return (img_file_path, align_file_path)

def get_meta_img_matches(folder_path, align_path_pattern, img_path_pattern):
    
    images_p = Path(folder_path)

    align_paths = list(images_p.glob(align_path_pattern))
    if len(align_paths) == 0:
        raise ValueError(f"No align files found with pattern {align_path_pattern}. Did you forget quotes around the wildcard pattern?")
    img_paths = list(images_p.glob(img_path_pattern))
    img_paths = list(set(img_paths) - set(align_paths))
    if len(img_paths) == 0:
        raise ValueError(f"No image files found with pattern {img_path_pattern}.  Did you forget quotes around the wildcard pattern?")

    matches = []
    for a in align_paths:
        for p in img_paths:
            if match_img_align(p, a):
                matches.append((p,a))
    if len(matches) == 0:
        raise ValueError("There were no matches between the align files and imgs files.")
    return matches

def helper(meta_path):
    meta_name = str(meta_path.name)
    if meta_name.startswith("Image") or meta_name.startswith("Mosaic"):
        return read_transform_inputs_datum(meta_path)
    elif meta_name.startswith("ScanImage"):
        return read_transform_inputs_img(meta_path)
    else:
        raise ValueError(f"{meta_name} did not start with an expected substring 'Image' 'Mosaic' or 'ScanImage'.")
        
def read_transform_inputs_datum(datum_meta_path):
    parser = et.XMLParser(encoding="utf-8")
    xtree = et.parse(datum_meta_path, parser=parser)
    root = xtree.getroot()
    return {
        "rotation" : float(root[0][0].text),
        "center_x" : float(root[0][1].text.split(",")[0]),
        "center_y" : float(root[0][1].text.split(",")[1]),
        "size_x" : float(root[0][2].text.split(",")[0]),
        "size_y" : float(root[0][2].text.split(",")[1]),
        "focus" : float(root[0][3].text)
    }
        
def read_transform_inputs_img(meta_path):
    """Reads xml info about the scanned image used to transform coordinates. 
    meta path should be a path to an align xml file that conforms to the schema 
    in this function.
    """
    xtree = et.parse(meta_path)
    root = xtree.getroot()
    center_info = root[0][2].text.split(",")
    size_info = root[0][3].text.split(",")
    extra_info = root[0][0].text.split(";")
    return {"rotation": float(root[0][1].text), 
           "center_x": float(center_info[0]),
           "center_y" : float(center_info[1]),
           "size_x" : float(size_info[0]),
           "size_y" : float(size_info[1]),
           "brightness": float(extra_info[0].split("=")[1]),
           "contrast": float(extra_info[1].split("=")[1]),
           "autoexposure": float(extra_info[2].split("=")[1]),
           "exposuretime": float(extra_info[3].split("=")[1])}


def folder_metadata_to_df(folder_path, align_path_pattern, img_path_pattern):
    
    matches = get_meta_img_matches(folder_path, align_path_pattern, img_path_pattern)

    image_df = pd.DataFrame(matches, columns=["img","meta"])
    # helper will read metadata depending on image type
    image_df = image_df.join(pd.json_normalize(image_df.meta.apply(helper)))

    image_df['source_shape'] = image_df.img.apply(lambda x: skio.imread(x).shape)

    image_df = image_df.join(pd.DataFrame(image_df['source_shape'].tolist(), index=image_df.index, columns=["source_size_y", "source_size_x", "source_size_band"]))
    
    return image_df

def calculate_transforms(image_df):
    """Calculates a transform tuple for each image referenced in the dataframe
    
    The format for the transform is (uperleftx, scalex, skewx, uperlefty, skewy, scaley) 
    and defines how to map pixel coordinates to CRS coordinates.
    """
    image_df['resolution_x'] = image_df['size_x'] / image_df['source_size_x']
    image_df['resolution_y'] = image_df['size_y'] / image_df['source_size_y']
    image_df['upleftx'] = image_df.center_x - image_df.size_x / 2
    image_df['uplefty'] = image_df.center_y - image_df.size_y / 2
    # Specify raster location through geotransform array
    # (uperleftx, scalex, skewx, uperlefty, skewy, scaley)
    image_df["affine_transform"] = image_df.apply(lambda row: affine.Affine(row['upleftx'], row['resolution_x'], row['rotation'], 
                                                                    row['uplefty'], row['rotation'], -row['resolution_y']), axis=1)
    return image_df

def georef_by_crs_img_meta(row, outfolder):
    """Georeferences to 2D coordinate reference system with upper left as origin.
    """
    src_filename = str(row["img"])
    
    if os.path.exists(outfolder) == False:
        print(f"outfolder {outfolder} did not already exist, creating it.")
        os.mkdir(outfolder)
    
    dst_filename = os.path.join(outfolder, os.path.basename(str(row['img'])).split(".")[0] + ".tif")
    
    # Opens source dataset
    src_ds = gdal.Open(src_filename)

    driver = gdal.GetDriverByName('GTiff')
    ds = driver.Create(dst_filename, xsize=int(row['source_size_x']), ysize=int(row['source_size_y']), bands=3)

    srs = osr.SpatialReference()
    srs.ImportFromEPSG(6507) # epsg code for 2D cartesian coordinates
    ds.SetProjection(srs.ExportToWkt())

    gt = list(row['affine_transform'])[0:6]
    print(f"referencing {row['img']} and {row['meta']}")
    ds.SetGeoTransform(gt)

    outband = ds.GetRasterBand(1)
    arr = skio.imread(src_filename)
    arr = np.moveaxis(arr, -1, 0)
    for i, band in enumerate(arr, 1):
        ds.GetRasterBand(i).WriteArray(band)

# def for_each_img(image_df, outfolder, funcs=[georef_by_crs_img_meta]):
#     """
#     Applies a list of funcs to the image_df. a func should only take the image_df as an argument and return nothing.
#     Main purpose is to save the georeferenced tifs, but other functions can be passed.
#     """
#     for func in funcs:
#         image_df.apply(func, axis=1)
        
def reference_all(infolder, outfolder, align_path_pattern="*.Align", img_path_pattern="ScanImage*.png"):
    """This spatially references all images in a folder and saves .tifs to another 
    folder. 
    
    A wildcard pattern is used to match each image (.bmp, .png. or .jpeg) to a 
    corresponding align file. Each image's align file must have the same unique 
    identifiers.
    For example: W235 9 51 191028195737 together form unique ids in the filename
    ScanImage_W235_9_51_Ablation_EndPattern_191028195737.png
    Align files must be in xml and must follow schemas supported by this script.
    
    Args:
        infolder str:
            The path to the folder that the images are in.
        outfolder str:
            The path to the folder to save the spatially referenced images.
        align_path_pattern str:
            wildcard pattern used to create a list of align files to match to
            image files. Defaults to "ScanImage*.Align"
        img_path_pattern str:
            wildcard pattern used to create a list of image files to match to
            align files. Defaults to "ScanImage*.png". All paths matching the 
            align_pattern_path will be removed from the list derived from this
            path, so that that a wildcard pattern of "*" can represent all 
            images.
    
    """
    print(f"Using wildcard patterns {align_path_pattern} and {img_path_pattern}")
    image_df = folder_metadata_to_df(infolder, align_path_pattern, img_path_pattern)
    image_df = calculate_transforms(image_df)
    image_df.apply(lambda row: georef_by_crs_img_meta(row, outfolder), axis=1)
    print(f"All done! Check results in {outfolder}")
        
    def cli_helper():
        fire.Fire(reference_all)

if __name__ == "__main__":
    #fire.Fire(reference_all)
    cli_helper()
