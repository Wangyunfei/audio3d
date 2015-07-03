# -*- coding: utf-8 -*-
"""
Created on Fri Jun  5 10:30:53 2015

@author: Felix Pfreundtner
"""

import scipy.io.wavfile
import struct
import numpy as np
import math
from error_handler import send_error
from scipy.fftpack import fft, ifft, fftfreq
import time


# @class <DspIn> This class contains all functions executed before the
#        convolution in the run-function of the Dsp-class. This includes
#        particularly
#        to read parameters of blocks and hrtfs, to read blocks and hrtfs
#        from their databases, to normalize hrtfs, round numbers and to
#        create all necessary kinds of windows.
class DspIn:
    ## Constructor of the DspIn class.
    def __init__(self, gui_dict_init, gui_settings_dict_init):
        # Dict with a key and two values for every hrtf to be fetched from the
        # database. The values are the max. values of the hrtfs of
        # each ear.
        self.hrtf_max_amp_dict = dict.fromkeys(gui_dict_init, [0, 0])
        # Dict with a key for every speaker and two values. These
        # are the max. values fetched from the speaker-file.
        self.sp_max_amp_dict = dict.fromkeys(gui_dict_init, [])
        # Standard samplerate, sampledepth
        self.wave_param_common = [44100, 16]
        # Set number of output blocks per second
        self.fft_blocksize = 1024
        # Number of Samples of HRTFs (KEMAR Compact=128, KEMAR Full=512)
        self.hrtf_database_name, self.hrtf_blocksize, \
        self.hrtf_blocksize_real, self.kemar_inverse_filter, \
        self.kemar_inverse_filter_active = \
            self.get_hrtf_param(gui_settings_dict_init)
        # read in whole hrtf datatabas from impulse responses in time domain
        self.hrtf_database_time = self.read_hrtf_database(gui_settings_dict_init)
        # bring whole hrtf database to frequency domain
        self.hrtf_database_fft = self.hrtf_database_fft()
        # Initialize a dict for the hrtf block values to be stored in.
        self.hrtf_block_fft_dict = dict.fromkeys(gui_dict_init, np.zeros((
            self.fft_blocksize, 2), dtype=np.complex128))
        # Define blocksize, blocktime, overlap and hopsize
        self.sp_blocksize, self.sp_blocktime, self.overlap, self.hopsize = \
            self.get_block_param(self.wave_param_common,
                                 self.hrtf_blocksize, self.fft_blocksize)
        # Get necessary parameters of input-file and store to sp_param-dict.
        self.sp_param = self.init_get_block(gui_dict_init)
        # read in whole wave file of all speakers
        self.sp_dict = self.read_sp(gui_dict_init)
        self.block_begin_end = self.init_set_block_begin_end(gui_dict_init)
        # initialize empty numpy array where to save samples of each
        # speaker block
        self.sp_block_dict = dict.fromkeys(gui_dict_init, np.zeros((
            self.sp_blocksize,), dtype=np.int16))
        # Temp Variable with zeros for faster fft convolution
        self.sp_block_sp_zeropadded = np.zeros((self.fft_blocksize, ),
                                           dtype='int16')
        # build a hann window with sp_blocksize
        self.hann = self.build_hann_window(self.sp_blocksize)

    ## @brief function rounds any input value to the closest integer
    # @details This function does a normal school arithmetic round (choose
    #          lower int until .4 and higher int from .5 on) and returns the
    #          rounded value. It is NOT equal to pythons round() method.
    # @retval <value> Is the rounded int of any input number.
    # @author Felix Pfreundtner
    def rnd(self, value):
        if value >= 0:
            if value - math.floor(value) < 0.5:
                value = math.floor(value)
            else:
                value = math.ceil(value)
        else:
            if value - math.floor(value) <= 0.5:
                value = math.floor(value)
            else:
                value = math.ceil(value)
        return value

    ## @brief Calculate and construct the hann window in dependency of
    #        sp_blocksize
    # @retval <hann_window> Numpy-array of the length of sp_blocksize
    # @author Felix Pfreundtner
    def build_hann_window(self, sp_blocksize):
        x = sp_blocksize
        hann_window = np.zeros((x,), dtype=np.float16)
        for n in range(x):
            hann_window[n, ] = 0.5 * (1 - math.cos(2 * math.pi * n / (x)))
        return hann_window

    ## @brief This function calculates the three block parameters necessary
    #        for the while-loop of the run-function.
    # @details This method uses the parameters of the input .wav-file and
    #          the blocksizes of the fft and the hrtf to calculate the
    #          blocksize and blocktime needed from the speaker.
    # @retval <sp_blocksize> Amount of samples taken from the input file per
    #         block
    #         <sp_blocktime> Time it takes to play one block in [s]
    #         <overlap> overlap between two binaural output blocks in decimal
    #         value [calculated default is 0.5]
    # @author Felix Pfreundtner
    def get_block_param(self, wave_param_common, hrtf_blocksize,
                        fft_blocksize):
        sp_blocksize = fft_blocksize - hrtf_blocksize + 1
        sp_blocktime = sp_blocksize / wave_param_common[0]
        # overlap in decimal 0
        overlap = (fft_blocksize - sp_blocksize) / fft_blocksize
        # overlap = 0
        hopsize = self.rnd((1 - overlap) * sp_blocksize)
        return sp_blocksize, sp_blocktime, overlap, hopsize

    ## @brief Initializes a list with the number of the first and last sample
    #         of the first block
    # @details This function calculates a list called block_begin_end containing
    #          two elements: [0] is the first sample of the first block,
    #          [1] is the last sample of the first block; The entries of
    #          following block will then be calculated by the
    #          set_block_begin_end-function.
    # @retval <block_begin_end> List of the first ([0]) and last ([0]) sample
    #         of the FIRST block.
    # @author Felix Pfreundtner
    def init_set_block_begin_end(self, gui_dict):
        block_begin_end = [int(-(self.sp_blocksize) * (1 - self.overlap)),
                           int((self.sp_blocksize) * (self.overlap))]
        return block_begin_end

    ## @brief Every while-loop the number of the first and last sample is
    #         calculated
    # @details This function replaces the values set by the
    #          init_set_block_begin_end-function every while-loop according to
    #          the current location in the speaker-file that needs to be
    #          read. Since the values are replaced, there are no input and
    #          output variables.
    # @author Felix Pfreundtner
    def set_block_begin_end(self):
        self.block_begin_end[0] += int(self.sp_blocksize * (1 - self.overlap))
        self.block_begin_end[1] += int(self.sp_blocksize * (1 - self.overlap))

    ## @brief Get all parameters for the hrtf set by the settings in gui
    # @details This function calculates all necessary parameters of the hrtf
    #          to be later able to get the correct hrtf-files for the
    #          convolution with the speaker-file signal.
    # @retval <hrtf_database_name> Tells which database the listener has chosen (
    #         available are: normal ear, big ear and a compact version)
    # @retval <hrtf_blocksize> Simply set to default value 513 since
    #         fft_blocksize is defaulted to 1024
    # @retval <kemar_inverse_filter> Boolean value that tells whether
    #         check-box in gui was activated or not
    # @author Felix Pfreundtner
    def get_hrtf_param(self, gui_settings_dict):
        hrtf_database_name = gui_settings_dict["hrtf_database"]
                # write variable which contains whether inverse filter is
        # activated in gui
        kemar_inverse_filter_active = gui_settings_dict["inverse_filter_active"]
        if hrtf_database_name == "kemar_normal_ear" or hrtf_database_name == \
                "kemar_big_ear":
            # wave hrtf size 512 samples: zeropad hrtf to 513 samples to
            # reach even sp_blocksize which is integer divisible by 2 (50%
            # overlap needed -> sp_blocksize/2)
            hrtf_blocksize_real = 512
            hrtf_blocksize = 513
            # get inverse minimum phase impulse response response of
            # kemar measurement speaker optimus pro 7 and truncate to
            # fft_blocksize
            _, kemar_inverse_filter = \
                scipy.io.wavfile.read(
                    "./kemar/full/headphones+spkr/Opti-minphase.wav")
            kemar_inverse_filter = \
                kemar_inverse_filter[0:self.fft_blocksize, ]
        if hrtf_database_name == "kemar_compact":
            # wave hrtf size 128 samples: zeropad hrtf to 513 samples to
            # reach even sp_blocksize which is integer divisible by 2 (50%
            # overlap needed -> sp_blocksize/2)
            hrtf_blocksize_real = 128
            hrtf_blocksize = 513
            # no inverse speaker impulse response of measurement speaker
            # needed (is already integrated in wave files of kemar compact
            # hrtfs)
            kemar_inverse_filter = np.zeros((self.fft_blocksize,),
                                            dtype=np.int16)
        return hrtf_database_name, hrtf_blocksize, hrtf_blocksize_real, \
               kemar_inverse_filter, kemar_inverse_filter_active

    ## @brief Preloads all hrtf Files
    # @author Felix Pfreundtner
    def read_hrtf_database(self, gui_dict_sp):
        angle_stepsize= 5
        angle_begin = 0
        # just look at horizontal plane
        elevation = 0
        number_of_hrtfs = 72
        hrtf_database_time = np.zeros((self.hrtf_blocksize, number_of_hrtfs),
                                            dtype=np.float32)
        if self.hrtf_database_name == "kemar_normal_ear":
            angle_end = 360
            for angle in range(0, angle_end, 5):
                hrtf_filename = "./kemar/full/elev" + str(elevation) + "/L" \
                                + str(elevation) + "e" +\
                                str(angle).zfill(3) + "a.wav"
                _, hrtf_database_time[:self.hrtf_blocksize_real,
                   angle/angle_stepsize]\
                    = \
                    scipy.io.wavfile.read(hrtf_filename)

        if self.hrtf_database_name == "kemar_big_ear":
            angle_end = 360
            for angle in range(0, angle_end, 5):
                hrtf_filename = "./kemar/full/elev" + str(elevation) + "/R" \
                                + str(elevation) + "e" +\
                                str(angle).zfill(3) + "a.wav"
                _, hrtf_database_time[:self.hrtf_blocksize_real, angle/angle_stepsize]\
                    = \
                    scipy.io.wavfile.read(hrtf_filename)
        if self.hrtf_database_name == "kemar_compact":
            angle_end = 180
            for angle in range(0, angle_end, 5):
                hrtf_filename = "./kemar/compact/elev" + str(elevation) + "/H" \
                                + str(elevation) + "e" +\
                                str(angle).zfill(3) + "a.wav"
                _, temp_hrtf_l_r = scipy.io.wavfile.read(hrtf_filename)
                hrtf_database_time[:self.hrtf_blocksize_real, angle/angle_stepsize] = \
                    temp_hrtf_l_r[:,0]
                hrtf_database_time[:self.hrtf_blocksize_real,
                (angle+180)/angle_stepsize] = \
                    temp_hrtf_l_r[:,1]
        return hrtf_database_time

    ## @brief brings the whole hrtf database in frequency domain
    # @author Felix Pfreundtner
    def hrtf_database_fft(self):
        hrtf_database_fft = np.zeros((self.fft_blocksize,
                                       self.hrtf_database_time.shape[1]),
                                       dtype=np.complex128)
        hrtf_zeropadded = np.zeros((self.fft_blocksize, ), dtype=np.int16)
        for angle_index in range (self.hrtf_database_time.shape[1]):
            hrtf_zeropadded[:self.hrtf_blocksize, ] = self.hrtf_database_time[:,
                                                  angle_index]
            hrtf_database_fft[:, angle_index] = fft(hrtf_zeropadded,
                                              self.fft_blocksize)
        return hrtf_database_fft




    ## @brief get 10 important parameters of the files to be played by the
    #         get_block_function
    # @details This method gets all important data from the .wav files that
    #          will be played by the speakers. Input is a gui_dict, containing
    #          the filename at place [2]. The output is another dict called
    #          sp_param, which holds one of the properties as values for each
    #          speaker given by the gui_dict.
    # @retval <sp_param> Returns a dictionary containing following values for
    #         each key [sp]
    # sp_param[sp][0] = total number of samples in the file
    # sp_param[sp][1] = sample-rate, default: 44100 (but adjustable later)
    # sp_param[sp][2] = number of bits per sample (8-/16-/??-int for one sample)
    # sp_param[sp][3] = number of channels (mono = 1, stereo = 2)
    # sp_param[sp][4] = format of file (< = RIFF, > = RIFX)
    # sp_param[sp][5] = size of data-chunk in bytes
    # sp_param[sp][6] = total-header-size (= number of bytes until data begins)
    # sp_param[sp][7] = bitfactor (8-bit --> 1, 16-bit --> 2)
    # sp_param[sp][8] = total number of bytes until data-chunk ends
    # sp_param[sp][9] = format character for correct encoding of data}
    # @author Matthias Lederle
    def init_get_block(self, gui_dict):
        # initialize dict with 10 (empty) values per key
        sp_param = dict.fromkeys(gui_dict, [None] * 10)
        # go through all speakers
        for sp in gui_dict:
            if gui_dict[sp][2] == 'unknown' or gui_dict[sp][2] == '':
                # ERROR message -- no file selected
                print("No file selected")
                # errmsg = "No audio source was selected. Please press " \
                # "'Reset' and add speaker(s) with valid pathname again."
                # self.signal_handler.send_error(errmsg)
            else:
                # open the file
                file = open(gui_dict[sp][2], 'rb')
                # checks whether file is RIFX or RIFF
                _big_endian = False
                str1 = file.read(4)
                if str1 == b'RIFX':
                    _big_endian = True
                if _big_endian:
                    sp_param[sp][4] = '>'
                else:
                    sp_param[sp][4] = '<'
                # jump to byte number 22
                file.seek(22)
                # get number of channels from header
                sp_param[sp][3] = struct.unpack(sp_param[sp][4] + "H",
                                                file.read(2))[0]
                # get samplerate from header (always 44100)
                sp_param[sp][1] = struct.unpack(sp_param[sp][4] + "I",
                                                file.read(4))[0]
                file.seek(34)  # got to byte 34
                # get number of sp_param_sp[2] per sample from header
                sp_param[sp][2] = struct.unpack(sp_param[sp][4] + "H",
                                                file.read(2))[0]
                # check in 2-byte steps, where the actual data begins
                # save distance from end of header in "counter"
                counter = 0
                checkbytes = b'aaaa'
                # go to byte where data-chunk begins and save distance in
                # "counter"
                while checkbytes != b'data':
                    file.seek(-2, 1)
                    checkbytes = file.read(4)
                    counter += 1
                # get data-chunk-size from the data-chunk-header
                sp_param[sp][5] = struct.unpack(sp_param[sp][4] + 'i',
                                                file.read(4))[0]
                # calculate total-header-size (no. of bytes until data begins)
                sp_param[sp][6] = 40 + (counter * 2)
                # calculate bitfactor
                sp_param[sp][7] = int(sp_param[sp][2] / 8)
                # calculate the total numbers of bytes until the end of
                # data-chunk
                sp_param[sp][8] = sp_param[sp][6] + sp_param[sp][5]
                # choose correct format character depending on number of bits
                # per sample
                if sp_param[sp][7] == 1:    # if bitfactor == 1
                    sp_param[sp][9] = "B"   # use format character "B"
                elif sp_param[sp][7] == 2:  # if bitfactor == 2
                    sp_param[sp][9] = "h"   # use format character "h"
                # calculate total number of samples of the file
                sp_param[sp][0] = int(sp_param[sp][5] / (sp_param[sp][2] / 8 *
                                                         sp_param[sp][3]))
                file.close()  # close file opened in the beginning

            # In case of error, send errormessage to gui
            # If samplerate is not 44100 Hz
            if not sp_param[sp][1] == 44100:
                print("error1")
                # errmsg = "Input signal doesn't have samplerate of 44100 " \
                #     "samples/sec. and can't be processed. Please choose " \
                #     "another input file."
                # self.signal_handler.send_error("error")

            # If bit format is not 8- or 16-bit/sample
            if not sp_param[sp][2] == 8 and not sp_param[sp][2] == 16:
                print("error2")
                # errmsg = "The bit-format of the samples is neither 8- nor " \
                #          "16-bit and can't be processed. Please choose " \
                #          "another input file."
                # self.signal_handler.send_error(errmsg)
            # If signal is neither mono nor stereo, send error message to gui.
            if not sp_param[sp][3] == 1 and not sp_param[sp][3] == 2:
                print("error3")
                # errmsg = "Input signal is neither mono nor stereo and
                # can't be processed. Please choose another input file."
                # self.signal_handler.send_error(errmsg)
        return sp_param

    ## @brief reads one block of samples
    # @details This method reads a block of samples of a speaker-.wav-file
    #          and writes in a numpyarray sp_block_dict[sp] (containing one
    #          16-bit-int for each sample) and a flag that tells whether the
    #          end of the file is reached or not. This function will be
    #          applied in the while loop of the dsp-class: I.e. a optimum
    #          performance is required.
    # @retval <continue_output> boolean value whether the last block of file
    #         was read or any other block
    # @author Matthias Lederle
    def read_sp(self, gui_dict):
        # initialize an empty array with blocksize sp_blocksize for every
        # speaker in dictionary sp_dict
        sp_dict = {}
        for sp in gui_dict:
            sp_dict[sp] = np.zeros((self.sp_param[sp][0],), dtype=np.int16)

        # scipy io reference function
        start = time.time()
        scipy_sp_dict_raw = {}
        scipy_sp_dict = {}
        for sp in gui_dict:
            _, scipy_sp_dict_raw[sp] = scipy.io.wavfile.read(gui_dict[sp][2])
            lenarray = len(scipy_sp_dict_raw[sp])
            # append zeros to scipy_sp_dict_raw to reach that output is
            # divideable by sp_blocksize
            if lenarray % self.sp_blocksize != 0:
                scipy_sp_dict[sp] = np.zeros((lenarray + self.sp_blocksize -
                                              lenarray % self.sp_blocksize, ),
                                             dtype=np.int16)
                scipy_sp_dict[sp][0:lenarray, ] = scipy_sp_dict_raw[sp]
            else:
                scipy_sp_dict[sp] = scipy_sp_dict_raw[sp]

        print("timer scipy in ms: " + str(int((time.time() - start) * 1000)))

        # start = time.time()
        # ## iterate over all speakers to read in all speaker wave files
        # for sp in sp_dict:
        #     # start reading at sample 0 in speaker wave file
        #     begin_block = 0
        #     # stop reading at last sample in speaker wave file
        #     end_block = self.sp_param[sp][0]
        #     continue_input = True
        #     # open file of current speaker here
        #     file = open(gui_dict[sp][2], 'rb')
        #     # calculate begin_block as byte-number
        #     first_byte_of_block = self.sp_param[sp][6] + (begin_block *
        #                                                   self.sp_param[sp][7] *
        #                                                   self.sp_param[sp][3])
        #     # calculate end_block as byte_number
        #     last_byte_of_block = self.sp_param[sp][6] + (end_block *
        #                                                  self.sp_param[sp][7]
        #                                                  * self.sp_param[sp][3])
        #     # go to first byte of block and start "reading"
        #     file.seek(first_byte_of_block)
        #     # if input file is mono, write sp_dict[sp] in this part
        #     if self.sp_param[sp][3] == 1:
        #         # if play is not yet at the end of the file use this
        #         # simple loop:
        #         if last_byte_of_block < self.sp_param[sp][8]:
        #             i = 0
        #             # while i < blocklength, read every loop one sample
        #             # !!!!Very often in while-loop!!!!
        #             while i < self.sp_blocksize:
        #                 sp_dict[sp][i, ] = struct.unpack(
        #                     self.sp_param[sp][4] + self.sp_param[sp][9],
        #                     file.read(self.sp_param[sp][7]))[0]
        #                 i += 1
        #         # if play has reached the last block of the file, do:
        #         else:
        #             # calculate remaining samples
        #             remaining_samples = int((self.sp_param[sp][8] -
        #                                      first_byte_of_block) / (
        #                 self.sp_param[sp][7] *
        #                 self.sp_param[sp][3]))
        #             i = 0
        #             # read remaining samples to the end, then set
        #             # continue_input
        #             # to "False"
        #             while i < remaining_samples:
        #                 sp_dict[sp][i, ] = struct.unpack(
        #                     self.sp_param[sp][4] + self.sp_param[sp][9],
        #                     file.read(self.sp_param[sp][7]))[0]
        #                 i += 1
        #             continue_input = False
        #     # If input file is stereo, make mono and write sp_dict[sp]
        #     elif self.sp_param[sp][3] == 2:
        #         # First: Write left and right signal in independent lists
        #         samplelist_of_one_block_left = []
        #         samplelist_of_one_block_right = []
        #         # set random value that cant be reached by (self.sp_param[
        #         # sp][5] - current_last_byte) (see below)
        #         remaining_samples = 10000
        #         if last_byte_of_block < self.sp_param[sp][8]:
        #             i = 0
        #             # while i < blocklength, read every loop one sample
        #             # !!!!!Very often executed!!!
        #             while i < self.sp_blocksize:
        #                 # read one sample for left ear and one for right ear
        #                 left_int = struct.unpack(self.sp_param[sp][4] +
        #                                          self.sp_param[sp][9],
        #                                          file.read(
        #                                              self.sp_param[sp][7]))[0]
        #                 right_int = struct.unpack(self.sp_param[sp][4] +
        #                                           self.sp_param[sp][9],
        #                                           file.read(
        #                                               self.sp_param[sp][7]))[0]
        #                 samplelist_of_one_block_left.append(left_int)
        #                 samplelist_of_one_block_right.append(right_int)
        #                 i += 1
        #         else:  # if we reached last block of file, do:
        #             # calculate remaining samples
        #             remaining_samples = int((self.sp_param[sp][8] -
        #                                      first_byte_of_block) / (
        #                 self.sp_param[sp][7] *
        #                 self.sp_param[sp][3]))
        #             i = 0
        #             # read remaining samples and write one to left and one
        #             # to right
        #             while i < remaining_samples:
        #                 left_int = struct.unpack(self.sp_param[sp][4] +
        #                                          self.sp_param[sp][9],
        #                                          file.read(
        #                                              self.sp_param[sp][7]))[0]
        #                 right_int = struct.unpack(self.sp_param[sp][4] +
        #                                           self.sp_param[sp][9],
        #                                           file.read(
        #                                               self.sp_param[sp][7]))[0]
        #                 samplelist_of_one_block_left.append(left_int)
        #                 samplelist_of_one_block_right.append(right_int)
        #                 i += 1
        #             continue_input = False
        #         # Second: Get mean value and merge the two lists and write in
        #         # sp_dict[sp]
        #         if remaining_samples == 10000:
        #             i = 0
        #             while i < self.sp_blocksize:
        #                 mean_value = int((samplelist_of_one_block_left[i] +
        #                                   samplelist_of_one_block_right[i]) / 2)
        #                 sp_dict[sp][i, ] = mean_value
        #                 i += 1
        #         else:
        #             i = 0
        #             while i < remaining_samples:
        #                 mean_value = int((samplelist_of_one_block_left[i] +
        #                                   samplelist_of_one_block_right[i]) / 2)
        #                 sp_dict[sp][i, ] = mean_value
        #                 i += 1
        #             continue_input = False
        #             # else:
        #             # an Matthias: Hier bitte eine Fehlerausgabe über
        #             # DspSignalHandler() schreiben (Fragen zu der Funktion ->
        #             # Huaijiang) --> Wird gemacht!
        #             # print("Signal is neither mono nor stereo(
        #             # self.sp_param[sp][3] != 1" or "2") and can't be
        #             # processed!")
        # file.close()
        # print runtime in milliseconds
        # print("timer get_sp in ms: " + str(int((time.time() - start) * 1000)))
        return scipy_sp_dict      # , scipy_sp_dict


    ## @brief Gets and reads the correct hrtf-file from database
    # @details
    # @author Felix Pfreundtner
    def get_hrtf_block_fft(self, gui_dict_sp, sp):
        # get filename of the relevant hrtf for each ear
        # the if-statement differentiates between "compact" and "normal/big"
        # version according to settings in gui
        rounddifference = gui_dict_sp[0] % 5
        # if angle from gui exactly matches angle of the file
        if rounddifference == 0:
            if gui_dict_sp[0] <= 180:
                angle_exact = gui_dict_sp[0]
            else:
                angle_exact = 360 - gui_dict_sp[0]

        # If gui's angle doesn't exactly match, go to closest angle
        # available in database
        else:
            if gui_dict_sp[0] <= 180:
                if rounddifference < 2.5:
                    angle_exact = gui_dict_sp[0] - rounddifference
                else:
                    angle_exact = gui_dict_sp[0] + 5 - rounddifference
            else:
                if rounddifference < 2.5:
                    angle_exact = 360 - gui_dict_sp[0] - rounddifference
                else:
                    angle_exact = 360 - gui_dict_sp[0] + 5 - rounddifference
        # get rounded integer angle
        angle = self.rnd(angle_exact)

        # get the maximum amplitude of the left ear hrtf time signal
        self.hrtf_max_amp_dict[sp][0] = np.amax(np.abs(self.hrtf_database_time[
                                                       :, angle/5]))
        # get left ear hrtf fft values
        self.hrtf_block_fft_dict[sp][:, 0] = self.hrtf_database_fft[:, angle/5]

        #increase angle about 180° to get hrtf information for the right ear
        angle = angle + 180
        if angle != 360:
             # get the maximum amplitude of the right ear hrtf time signal
            self.hrtf_max_amp_dict[sp][1] = np.amax(np.abs(
                self.hrtf_database_time[:, angle/5]))
            # get right ear hrtf fft values
            self.hrtf_block_fft_dict[sp][:, 1] = self.hrtf_database_fft[:, angle/5]
        else:
            # get the maximum amplitude of the right ear hrtf time signal
            self.hrtf_max_amp_dict[sp][1] = np.amax(np.abs(
                self.hrtf_database_time[:, 0]))
            # get right ear hrtf fft values
            self.hrtf_block_fft_dict[sp][:, 1] = self.hrtf_database_fft[:, 0]

    ## @author Matthias Lederle
    def get_sp_block(self, sp):
        # if current block end is smaller than last sample in sp
        if self.block_begin_end[1] <= self.sp_param[sp][0]:
            self.sp_block_dict[sp] = self.sp_dict[sp][self.block_begin_end[
                0]: self.block_begin_end[1], ]
            continue_input = True
        # if current block end is LARGER, we enter the else-condition
        else:
            self.sp_block_dict[sp] = np.zeros((self.sp_blocksize),
                                              dtype=np.int16)
            self.sp_block_dict[sp][0:self.sp_param[sp][0] -
                                   self.block_begin_end[0], ] = self.sp_dict[
                sp][self.block_begin_end[0]:self.sp_param[sp][0], ]
            continue_input = False
        self.sp_max_amp_dict[sp] = np.amax(np.abs(self.sp_block_dict[sp][:, ]))
        return continue_input

    ## @brief Normalize the .wav-signal to have maximum of int16 amplitude
    # @details If the input-flag normalize_flag_sp is True, measure the
    #          maximum amplitude occurring in the .wav-file. After that,
    #          reduce all entries of sp_block_dict by the ratio that
    #          decreases the max value to 2^15-1
    # @author Felix Pfreundtner
    def normalize(self, normalize_bool, sp):
        if normalize_bool is True:
            # take maximum amplitude of original wave file of raw sp block
            max_amplitude_input = self.sp_max_amp_dict[sp]
            if max_amplitude_input != 0:
                # normalize to have the maximum int16 amplitude
                max_amplitude_output = 32767
                sp_block_dict_sp_norm = self.sp_block_dict[sp] / (
                    max_amplitude_input /
                    max_amplitude_output)
                self.sp_block_dict[sp] = sp_block_dict_sp_norm
                self.sp_block_dict[sp] = self.sp_block_dict[sp].astype(
                    np.int16, copy=False)
                self.sp_max_amp_dict[sp] = np.amax(np.abs(self.sp_block_dict[sp]
                                                          [:, ]))

    ## @author Felix Pfreundtner
    def apply_window_on_sp_block(self, sp):
        self.sp_block_dict[sp] = self.sp_block_dict[sp] * self.hann
        self.sp_block_dict[sp] = self.sp_block_dict[sp].astype(np.int16)


    # @brief Function convolves hrtf and data of the music file
    # @details Function takes one hrtf block and one data block (their size
    # is defined by fft_blocksize), normalizes their values to int16-signals
    # and then executes the convolution. After that, the signal is
    # retransformed to  time-domain and normalized again. The final values
    # are written then to the binaural_block_dict.
    # @author Felix Pfreundtner
    def fft_convolution(self, sp_spectrum_dict_sp, hrtf_spectrum_dict_sp_l_r,
                     binaural_block_dict_sp, sp, l_r):

        # Do for speaker sp zeropadding: zeropad speaker (mono input)
        self.sp_block_sp_zeropadded[0:self.sp_blocksize, ] = \
            self.sp_block_dict[sp]
        # bring time domain input to to frequency domain
        sp_block_fft_sp = fft(self.sp_block_sp_zeropadded, self.fft_blocksize)

        # save fft magnitude spectrum of sp_block in sp_spectrum and
        # hrtf_block in hrtf_spectrum to be shown by gui
        # create array of all calculated FFT frequencies
        freq_all = fftfreq(self.fft_blocksize, 1 / self.wave_param_common[0])
        # set position of only positive frequencies (neg. frequencies redundant)
        position_freq = np.where(freq_all >= 0)
        # set array of only positive FFT frequencies (neg. frequ. redundant)
        freqs = freq_all[position_freq]
        sp_spectrum_dict_sp[:, 0] = freqs
        hrtf_spectrum_dict_sp_l_r[:, 0] = freqs
        # get magnitued spectrum of sp_block
        sp_magnitude_spectrum = abs(sp_block_fft_sp[position_freq])
        # normalize spectrum to get int16 values
        max_amplitude_output = 32767
        max_amplitude_sp_magnitude_spectrum = np.amax(np.abs(
            sp_magnitude_spectrum))
        if max_amplitude_sp_magnitude_spectrum != 0:
            # get magnitude spectrum of hrtf-block
            sp_spectrum_dict_sp[:, 1] = sp_magnitude_spectrum / (
                max_amplitude_sp_magnitude_spectrum / self.sp_max_amp_dict[sp] *
                max_amplitude_output)
        hrtf_magnitude_spectrum = abs(self.hrtf_block_fft_dict[sp][:, l_r][
                                          position_freq])
        max_amplitude_hrtf_magnitude_spectrum = np.amax(np.abs(
            hrtf_magnitude_spectrum))
        if max_amplitude_hrtf_magnitude_spectrum != 0:
            hrtf_spectrum_dict_sp_l_r[:, 1] = hrtf_magnitude_spectrum\
                / (max_amplitude_hrtf_magnitude_spectrum /
                   self.hrtf_max_amp_dict[sp][l_r] * max_amplitude_output)
        sp_spectrum_dict_sp[0, 1] = 0
        hrtf_spectrum_dict_sp_l_r[0, 1] = 0

        # execute convolution of speaker input and hrtf input: multiply
        # complex frequency domain vectors
        binaural_block_sp_frequency = sp_block_fft_sp * \
                                      self.hrtf_block_fft_dict[sp][:, l_r]

        # if kemar full is selected furthermore convolve with (approximated
        #  1024 samples) inverse impulse response of optimus pro 7 speaker
        if self.kemar_inverse_filter_active:
            binaural_block_sp_frequency = binaural_block_sp_frequency * fft(
                self.kemar_inverse_filter, self.fft_blocksize)

        # bring multiplied spectrum back to time domain, disneglected small
        # complex time parts resulting from numerical fft approach
        binaural_block_sp_time = ifft(binaural_block_sp_frequency,
                                      self.fft_blocksize).real

        # normalize multiplied spectrum back to 16bit integer, consider
        # maximum amplitude value of sp block and hrtf impulse to get
        # dynamical volume output
        binaural_block_sp_time_max_amp = int(np.amax(np.abs(
            binaural_block_sp_time)))
        binaural_block_sp_time = binaural_block_sp_time / (
            binaural_block_sp_time_max_amp / self.sp_max_amp_dict[sp] /
            self.hrtf_max_amp_dict[sp][l_r] * 32767)
        binaural_block_dict_sp[:, l_r] = \
            binaural_block_sp_time.astype(np.int16)
        return binaural_block_dict_sp