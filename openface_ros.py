#!/usr/bin/env python2
#
# Example to classify faces.
# Brandon Amos
# 2015/10/11
#
# Copyright 2015-2016 Carnegie Mellon University
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import time
import argparse
import cv2
import os
import pickle
from operator import itemgetter
import numpy as np
np.set_printoptions(precision=2)
import pandas as pd
import dlib
import openface

from sklearn.pipeline import Pipeline
from sklearn.lda import LDA
from sklearn.preprocessing import LabelEncoder
from sklearn.svm import SVC
from sklearn.grid_search import GridSearchCV
from sklearn.mixture import GMM
from sklearn.tree import DecisionTreeClassifier
from sklearn.naive_bayes import GaussianNB
#ros wrapper
import rospy
from sensor_msgs.msg import Image, CompressedImage
from cv_bridge import CvBridge, CvBridgeError
from std_msgs.msg import String, UInt16, Float64, Bool,UInt8
from openface4ARM.srv import *
bridge = CvBridge()
count = 0
trackingFace = 0
rec_mode = False
training_mode = False

fileDir = os.path.dirname(os.path.realpath(__file__))
modelDir = os.path.join(fileDir, 'models')
dlibModelDir = os.path.join(modelDir, 'dlib')
openfaceModelDir = os.path.join(modelDir, 'openface')
pickleDir = os.path.join(fileDir, 'data/mydataset/banana_feature')
recDir = 'data/mydataset/banana_rec'
featureDir = 'data/mydataset/banana_feature'
path = ''
images_required = 10.0
transmit_progress = 0
dlibFacePredictor = os.path.join(dlibModelDir, "shape_predictor_68_face_landmarks.dat")
networkModel = os.path.join(openfaceModelDir, 'nn4.small2.v1.t7')
imgDim = 96

def image_callback(msg):
    global count
    global trackingFace
    banana = time.strftime("%H:%M:%S")
    rgbImg = bridge.compressed_imgmsg_to_cv2(msg, "rgb8")
    if rec_mode == True:
    	infer(rgbImg)
    if training_mode == True:	
        if count < images_required:
            try:
                # Convert your ROS Image message to OpenCV2
	        start = time.time()
	        if not trackingFace:
		    bb = align.getLargestFaceBoundingBox(rgbImg)
		    if bb is not None:
		        tracker.start_track(rgbImg,dlib.rectangle(bb.left(),bb.top(),bb.right(),bb.bottom()))
		        rospy.loginfo("face detection took {} seconds.".format(time.time() - start))
		        trackingFace = 1
		    else:
		        rospy.loginfo("unable to detect your face, please face the camera")
	        else:
		    trackingQuality = tracker.update(rgbImg)
		    if trackingQuality >= 8.75:
		        bb = tracker.get_position()
		        bb = dlib.rectangle(int(bb.left()),int(bb.top()),int(bb.right()),int(bb.bottom()))
		        outRgb = align.align(imgDim, rgbImg, bb,
                	    landmarkIndices=openface.AlignDlib.OUTER_EYES_AND_NOSE)
		        rospy.loginfo("face tracking and align took {} seconds.".format(time.time() - start))
		        count = count + 1
		        rospy.loginfo("Received {} images!".format(count))
		        outBgr = cv2.cvtColor(outRgb, cv2.COLOR_RGB2BGR)
		        #shape = predictor(rgbImg, bb)
		        cv2.imwrite(os.path.join(path,'IMAGE%s.jpeg' %count), outBgr)
		        image_progress = count / images_required * 100
		        pub.publish(image_progress)
		        faceImg = bridge.cv2_to_imgmsg(outBgr, "bgr8")
		        face_pub.publish(faceImg)
		    else:
		        rospy.loginfo("fail to track, redetecting face")
		        trackingFace = 0
            except CvBridgeError, e:
                print(e)

def getRep(rgbImg):
    global trackingFace
    start = time.time()
    if not trackingFace:
        # Get the largest face bounding box
        bb = align.getLargestFaceBoundingBox(rgbImg) #Bounding box
        if bb is not None:
            tracker.start_track(rgbImg,dlib.rectangle(bb.left(),bb.top(),bb.right(),bb.bottom()))
            trackingFace = 1
        else:
            motion_detected = False
            rospy.loginfo("unable to detect your face, please face the camera")
	    return []
    else:
        trackingQuality = tracker.update(rgbImg)
        if trackingQuality >= 8.75:
            bb = tracker.get_position()
            bb = dlib.rectangle(int(bb.left()),int(bb.top()),int(bb.right()),int(bb.bottom()))
        else:
            rospy.loginfo("unable to detect your face, please face the camera")
            trackingFace = 0
            motion_detected = False
            return []
    rospy.loginfo("Face detection took {} seconds.".format(time.time() - start))
    start = time.time()
    alignedFace = align.align(imgDim, rgbImg, bb,
            landmarkIndices=openface.AlignDlib.OUTER_EYES_AND_NOSE)
    if alignedFace is None:
        return []
    bgrImg = cv2.cvtColor(alignedFace, cv2.COLOR_RGB2BGR)
    faceImg = bridge.cv2_to_imgmsg(bgrImg, "bgr8")
    face_pub.publish(faceImg)
    rospy.loginfo("Alignment took {} seconds.".format(time.time() - start))
    start = time.time()
    reps = []
    reps.append(net.forward(alignedFace))
    rospy.loginfo("Neural network forward pass took {} seconds.".format(time.time() - start))
    return reps

def train_callback(msg):
    global training_mode
    global rec_mode
    training_mode = True
    rec_mode = False
    global path
    global count 
    count = 0
    #path = ('data/mydataset/banana_aligned/{}/{}'.format(msg.data,msg.data))
    path = ('data/mydataset/banana_aligned/{}'.format(msg.data))
    if not os.path.exists(path):
        os.makedirs(path)

    os.system('rm data/mydataset/banana_aligned/cache.t7')
    while not rospy.is_shutdown():
    	if count == images_required:
	    start = time.time()
	    os.system('./batch-represent/main.lua -outDir ./data/mydataset/banana_feature -data ./data/mydataset/banana_aligned')
	    #os.system('./batch-represent/main.lua -outDir ./data/mydataset/banana_feature -data ./data/mydataset/banana_aligned/{}'.format(msg.data))
	    #test.lua is for register new member only
	    #os.system('./batch-represent/test.lua -outDir ./data/mydataset/banana_feature -data ./data/mydataset/banana_aligned/{}'.format(msg.data))
	    rospy.loginfo("Feature generation took {} seconds".format(time.time()-start))
	    rospy.loginfo("Loading embeddings.")
	    fname = "{}/labels.csv".format(featureDir)
	    labels = pd.read_csv(fname, header=None).as_matrix()[:, 1]
	    labels = map(itemgetter(1),
		         map(os.path.split,
		             map(os.path.dirname, labels)))  # Get the directory.
	    fname = "{}/reps.csv".format(featureDir)
	    embeddings = pd.read_csv(fname, header=None).as_matrix()
	    le = LabelEncoder().fit(labels)
	    labelsNum = le.transform(labels)
	    nClasses = len(le.classes_)
	    rospy.loginfo("Training for {} classes.".format(nClasses))
	    clf = SVC(C=1, kernel='linear', probability=True)
	    clf.fit(embeddings, labelsNum)
	    fName = "{}/classifier.pkl".format(featureDir)
	    rospy.loginfo("Saving classifier to '{}'".format(fName))
	    with open(fName, 'w') as f:
		pickle.dump((le, clf), f)
	    pub1.publish(100)
	    break

def rec_callback(msg):
    global rec_mode
    global training_mode
    training_mode == False
    if msg.data == True:
	rec_mode = True
	rospy.loginfo('Starting face recognition mode')
    else:
    	rec_mode = False
	rospy.loginfo('Stopping face recognition mode')

def infer(img):
        with open(os.path.join(pickleDir,'classifier.pkl'), 'r') as f:
            (le, clf) = pickle.load(f)
	reps = getRep(img)
	for r in reps:
	    rep = r.reshape(1, -1)
	    predictions = clf.predict_proba(rep).ravel()
	    maxI = np.argmax(predictions)
	    person = le.inverse_transform(maxI)
	    confidence = predictions[maxI]
	    pub2.publish(person)

if __name__ == '__main__':
    if not os.path.exists(recDir):
        os.makedirs(recDir)
    rospy.init_node('people_rec')
    pub = rospy.Publisher('capturingProgress', UInt8, queue_size=1)
    pub1 = rospy.Publisher('trainingProgress', UInt8, queue_size=1)
    pub2 = rospy.Publisher('recognitionResults', String, queue_size=1)
    face_pub = rospy.Publisher('croppedFace', Image, queue_size=1)
    train_topic = "cmdTraining"
    rec_topic = "cmdRecognition"
    image_topic = "croppedImages/compressed"
    rospy.Subscriber(image_topic, CompressedImage, image_callback)
    rospy.Subscriber(train_topic, String, train_callback)    
    rospy.Subscriber(rec_topic, Bool, rec_callback)
    align = openface.AlignDlib(dlibFacePredictor)
    net = openface.TorchNeuralNet(networkModel, imgDim=imgDim)
    tracker = dlib.correlation_tracker()
    predictor = dlib.shape_predictor(dlibFacePredictor)
    #win = dlib.image_window()

    rospy.spin() 
