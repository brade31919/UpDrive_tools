# ===================================================
# @author    Hao-Chih Lin
# @email     hlin@ethz.ch
# @author    Juan-Ting Lin
# @email     julin@ethz.ch
#
# Copyright (C) 2019 HaoChih Lin, Juan-Ting Lin
# All rights reserved. (Apache License 2.0)
# ===================================================

from __future__ import print_function
from __future__ import absolute_import
from __future__ import division

import os
import sys
import cv2
import yaml
import numpy as np
import argparse
from collections import Counter

# Global Constant
CAMERA_INDEX_DICT = {'front': 0, 'left': 1, 'rear': 2, 'right': 3}

# @brief Function for converting calibration parameters from given yaml dict
# @param calibration_dict: the dict generated by yaml module (from specificed file)
# @param camera_index: the index of which camera model will be converted  
# @param output_scale: the scale factor for resizing the output undistorted image  
# @return list of matrix required by undistortion process ([] means errors)
def camera_matrix(calibration_dict, camera_index, output_scale):
    try:    
        camera_model = calibration_dict["ncameras"][0]["cameras"][int(camera_index)]["camera"]
        
        K = np.array([[camera_model["intrinsics"]["data"][1], 0, camera_model["intrinsics"]["data"][3]],
                      [0, camera_model["intrinsics"]["data"][2], camera_model["intrinsics"]["data"][4]],
                      [0, 0, 1]])

        K_scaled = K.copy()
        K_scaled[0][0] = K_scaled[0][0]/float(output_scale)
        K_scaled[1][1] = K_scaled[1][1]/float(output_scale)

        D = np.asarray(camera_model["distortion"]["parameters"]["data"])[:, np.newaxis]
        xi = np.asarray(camera_model["intrinsics"]["data"][0])
    except:
        print("[Error] Can not extract camera model properly!")
        return []

    return [K, D, xi, K_scaled]


# @brief Function for undistoring the image from given calibration parameters
# @param image_path: the file path for the distorted image
# @param camera_model: the list of calibration parameters [K, D, xi, K_scaled]
# @return undistorted image (None for internal errors)
def undistort(image_path, camera_model, verbose=False):
    # Check calibration parameters
    if len(camera_model) != 4:
        print("[Error] Wrong calibration parameters (total size)!")
        return None

    K = camera_model[0]
    D = camera_model[1]
    xi = camera_model[2]
    K_scaled = camera_model[3]

    if K.shape != (3,3) or D.shape != (4,1) or xi.shape != () or K_scaled.shape != (3,3):
        print("[Error] Wrong calibration parameters (shapes)!")
        return None

    # Read in image
    image = cv2.imread(image_path)
    if image is None:
        print("[Error] Can not load image from path!")
        return None

    # Perform calibration
    map1, map2	=	cv2.omnidir.initUndistortRectifyMap(K, D, xi, np.eye(3), K_scaled, (image.shape[1], image.shape[0]), cv2.CV_16SC2, cv2.omnidir.RECTIFY_PERSPECTIVE)
    undistorted_image = cv2.remap(image, map1, map2, interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT)

    if verbose:
        print("\t Finish processing image %s"%(os.path.basename(image_path)))
    
    return undistorted_image


# @brief The main function for auto-undistorting all images inside specified folders
def main():
    # Setup command line arguments
    argument = argparse.ArgumentParser()
    argument.add_argument("-inputs_dir", help="specify the directory of input images (distorted), it should contain 4 sub-folders")
    argument.add_argument("-outputs_dir", help="specify the directory of output images (undistorted), it will create 4 sub-folders")
    argument.add_argument("-yaml_file", help="specify the path of calibration .yaml file (follow 'ncamera' format)")
    argument.add_argument("--scale", type=int, default=5, help="specify the scale of undistorted image (default: 5")
    argument.add_argument("--v", help="set verbose as true", action="store_true")
    args = argument.parse_args()
    verbose = args.v
    output_scale = float(args.scale)
    print("[MAIN] ===== Start Auto-Undistortion Process =====")
    if verbose:
        print("[DEBUG] ===== The command arguments =====")
        print("[DEBUG] The inputs_dir: " + args.inputs_dir)
        print("[DEBUG] The outputs_dir: " + args.outputs_dir)
        print("[DEBUG] The yaml_file: " + args.yaml_file)
        print("[DEBUG] The scale: " + str(output_scale))

    # Check yaml file exist and validate the format
    if not os.path.isfile(args.yaml_file):
        print("[Error] The yaml_file not found!")
        sys.exit()
    document = open(args.yaml_file, 'r')
    try:
        calibration_parameters = yaml.safe_load(document)
    except yaml.YAMLError as exc:
        print(exc)
        print("[Error] The yaml_file unvalidated!")
        sys.exit()
    if verbose:
        print("[DEBUG] Calibration file context:")
        print(calibration_parameters)
    
    # Check the inputs folder and its sub-folders (rear, front, right and left)
    expected_subfolders_list = list(CAMERA_INDEX_DICT.keys())
    subfolders_list = [os.path.realpath(x[0]) for x in os.walk(args.inputs_dir)]
    if len(subfolders_list) == 0:
        print("[Error] The inputs_dir not exists!")
        sys.exit()
    if len(subfolders_list) != len(expected_subfolders_list) + 1:
        print("[Error] The inputs_dir should has " + str(len(expected_subfolders_list)) + " sub-folders!")
        sys.exit()

    subfolders_list.pop(0) # remove the first item (parent path)
    if Counter([os.path.basename(x) for x in subfolders_list]) != Counter(expected_subfolders_list):
        print("[Error] The input sub-folders do not match the expected name list!")
        sys.exit()

    # Check and create the output sub-folders
    try:
        os.mkdir(args.outputs_dir)
    except OSError:
        if verbose:
            print("[WARN] The output directory already exists!")

    outputs_directory = os.path.realpath(args.outputs_dir)
    for sub_name in expected_subfolders_list:
        try:
            os.mkdir(outputs_directory + '/' + sub_name)
        except OSError:  
            print("[Error] The output sub-folder already exists (for data safe, stop the process)!")
            sys.exit()

    # Loop for undistortion process
    for subfolder_directory in subfolders_list:
        print("[MAIN] Undistorting the images inside: " + subfolder_directory + " ...")
        subfolder_name = os.path.basename(subfolder_directory)
        camera_index = CAMERA_INDEX_DICT[subfolder_name]
        camera_model = camera_matrix(calibration_parameters, camera_index, output_scale)
        if len(camera_model) != 4:
            print("[Error] The camera model of index: " + str(camera_index) + " not found !")
            sys.exit()

        images_list = []
        try:
            for file in sorted(os.listdir(subfolder_directory)):
                #ipdb.set_trace()
                if file.endswith(".png"):
                    image_full_path = subfolder_directory + '/' + file
                    images_list.append(image_full_path)
                    undistorted_image = undistort(image_full_path, camera_model, verbose=verbose)
                    if undistorted_image is None:
                        print("[WARN] Pass the image with undistortion process fail: " + file)
                    else:
                        result = cv2.imwrite(outputs_directory + '/' + subfolder_name + '/' +  file, undistorted_image)
                        if result == False:
                            print("[WARN] Fail to save the undistorted image: " + file)
        except:
            print("[WARN] Failure for undistortion process, current image: " + images_list[-1])
          
    print("[MAIN] Finished all tasks, outputs: " + outputs_directory)

if __name__ == '__main__':
    main()
