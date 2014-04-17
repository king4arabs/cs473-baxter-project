#!/usr/bin/env python

"""The experiment module"""

import os
import time
import subprocess
import sys
import ConfigParser

import rospy

import baxter_interface

from position_control import PositionControl
from webcam import Webcam
from cs473vision.cs473vision.view_baxter import BaxterObjectView

CONFIG = './src/cs473-baxter-project/cs473_baxter/config/config'

class BoxFit(object):
    """The primary module for running compression trials.
    Links the webcam, vision segmentation, and actuation
    modules together.
    """
    def __init__(self):
        rospy.init_node("cs473_box_fit")

        self.is_glove_attached()

        # Verify robot is enabled
        print "Getting robot state..."
        self._rs = baxter_interface.RobotEnable()
        self._init_state = self._rs.state().enabled
        print "Enabling robot..."
        self._rs.enable()
        print "Running. Ctrl-c to quit"

        self.p_ctrl = PositionControl('right')

        self.img_dir = self._create_img_dir()

    def is_glove_attached(self):
        """Prompt the user to check if Baxter's pusher glove
        is attached or not. Exit the process if it is not.
        """
        glove_on = raw_input("Is Baxter's glove attached? (y/n): ")
        if glove_on is not "y":
            print "\nERROR: Attach glove with glove.py before running BoxFit."
            sys.exit(1)

    def _create_img_dir(self):
        """Creates a timestamped folder in the img_dir directory
        that stores the images of one compression run.
        """
        config = ConfigParser.ConfigParser()
        config.read(CONFIG)
        base_img_dir = config.get("IMAGE_DIRECTORY", "base_img_dir")
        img_dir = ''.join([base_img_dir, time.strftime("%d%m%Y_%H-%M-%S")])
        os.mkdir(img_dir)
        return img_dir

    def set_neutral(self):
        """Move arm(s) to initial joint positions."""
        self.p_ctrl.set_neutral()

    def compress_object(self):
        """Compress an object while opening the webcam to take
        snapshots during the compression.
        """
        joint_pos = self.p_ctrl.get_jp_from_file('RIGHT_ARM_INIT_POSITION')
        self.p_ctrl.move_to_jp(joint_pos)

        # Suppress collision detection and contact safety
        contact_safety_proc = subprocess.Popen(['rostopic', 'pub',
            '-r', '10',
            '/robot/limb/right/suppress_contact_safety',
            'std_msgs/Empty'])

        time_data = open(os.path.join(self.img_dir, 'timestamps.txt'), 'a+')
        r_data = open(os.path.join(self.img_dir, 'rostopic_data.txt'), 'a+')

        time_data.write('webcam: ' + str(rospy.Time.now().nsecs) + '\n')
        w_proc = subprocess.Popen(['rosrun', 'cs473_baxter', 'webcam.py',
            "-d", self.img_dir,
            "-t", "12"])

        time.sleep(2) # Buffer time for webcam subprocess to get ready

        time_data.write('rostopic: ' + str(rospy.Time.now().nsecs) + '\n')
        r_proc = subprocess.Popen(['rostopic', 'echo',
            '/robot/limb/right/endpoint_state'],
            stdout=r_data)

        time_data.write('compress: ' + str(rospy.Time.now().nsecs) + '\n')
        self.p_ctrl.move_to_jp(
            self.p_ctrl.get_jp_from_file('RIGHT_ARM_COMPRESS_POSITION'),
            timeout=10, speed=0.05)

        time.sleep(1.5)

        joint_pos = self.p_ctrl.get_jp_from_file('RIGHT_ARM_INIT_POSITION')
        self.p_ctrl.move_to_jp(joint_pos)

        contact_safety_proc.terminate()
        r_proc.terminate()
        w_proc.terminate()
        time_data.close()

    def clean_shutdown(self):
        """Clean up after shutdown callback is registered."""
        print "\nExiting box fit routine..."
        if not self._init_state and self._rs.state().enabled:
            print "Disabling robot..."
            self._rs.disable()

def main():
    """Experiment module"""
    box_fit = BoxFit()
    camera = Webcam(box_fit.img_dir)
    rospy.on_shutdown(box_fit.clean_shutdown)
    box_fit.set_neutral()

    print 'Taking snapshot of the background.'
    camera.open()
    time.sleep(2)
    camera.take_snapshot('background.png')
    camera.close()

    raw_input("Place reference object in center. Press ENTER when finished.")
    camera.open()
    time.sleep(2)
    camera.take_snapshot('reference.png')
    camera.close()
    raw_input("Remove the reference object. Press ENTER when finished.")

    print 'Taking snapshot of just the arm'
    joint_pos = box_fit.p_ctrl.get_jp_from_file('RIGHT_ARM_INIT_POSITION')
    box_fit.p_ctrl.move_to_jp(joint_pos)
    camera.open()
    camera.take_snapshot('arm.png')
    camera.close()
    box_fit.set_neutral()

    raw_input("Place object alone in center. Press ENTER when finished.")
    camera.open()
    camera.take_snapshot('object.png')
    camera.close()

    box_fit.compress_object()

    # Do image stuff

    base = box_fit.img_dir + "/"
    bg_path = base + '/background.png'
    arm_path = base + '/arm.png'
    uncompressed_path =  base + '/object.png'

    baxter_obj = BaxterObjectView(bg_path)
    baxter_obj.set_arm_image(arm_path)
    #baxter_obj.set_arm_color((h, s, v), (h, s, v))
    baxter_obj.set_uncompressed_image(uncompressed_path)

    print "Uncompressed size: " + str(baxter_obj.get_uncompressed_size())

    for i in range(999):
        path = base + "/compression" + ('%03d' % i) + ".png"
        if os.path.isfile(path):
            baxter_obj.set_compressed_image(path, force=-1)
        else:
            break

    print "Compressed size: " + str(baxter_obj.get_compressed_size())

    baxter_obj.export_sizes("./sizes.txt")

    #baxter_obj.display_results()

if __name__ == '__main__':
    main()
