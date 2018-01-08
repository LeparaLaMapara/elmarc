import numpy as np
from sklearn.svm import SVC
from sklearn.metrics import accuracy_score
import tensorflow as tf
import librosa
import pickle
import time
import os
from sklearn.model_selection import GridSearchCV
from sklearn.metrics import classification_report
from sklearn.cross_validation import PredefinedSplit

config = {

    'experiment_name': 'order_istrainFalse_noDrop_batch200',
    'features_type': 'CNN',

    'load_extracted_features': False,
    'audio_path': '/mnt/vmdata/users/jpons/GTZAN_debug/',
    'audios_list': '/mnt/vmdata/users/jpons/GTZAN_debug_partitions/list.txt',
    'save_extracted_features_folder': '../data/GTZAN/features/', 
   
    'CNN': {
        'n_mels': 96,
        'n_frames': 1360,
        'selected_features_list': [0, 1, 2, 3, 4],
        'batch_size': 1,
        'is_train': False
    },

    'sampling_rate': 12000
}


svm_params = [

    {'kernel': ['rbf'],
     'gamma': [1 / (2 ** 3), 1 / (2 ** 5), 1 / (2 ** 7), 1 / (2 ** 9), 1 / (2 ** 11), 1 / (2 ** 13), 'auto'],
     'C': [0.1, 2.0, 8.0, 32.0]},

    {'kernel': ['linear'],
     'C': [0.1, 2.0, 8.0, 32.0]}
]


# CNNs

def iterate_minibatches(prefix, audio_paths_list, batchsize):
    for start_i in range(0, len(audio_paths_list) - batchsize + 1, batchsize):          
        first = True
        ground_truth = []
        for i in range(start_i,start_i + batchsize,1):
            file_path = prefix + audio_paths_list[i]
            file_path = file_path[:-1] # remove /n
            tag = audio_paths_list[i][:audio_paths_list[i].rfind('/')]
            print(file_path)
            if first:
                data = compute_spectrogram(file_path,config['sampling_rate'])
                first = False
            else:
                data = np.append(data,compute_spectrogram(file_path,config['sampling_rate']), axis=0)
            ground_truth.append(gtzan_ground_truth(tag))
        yield data, ground_truth
    
    # TODO: get resting samples


def format_cnn_data(prefix, list_audios):
    l_audios = open(list_audios, 'r')
    audio_paths_list = []
    for s in l_audios:
        audio_paths_list.append(s)
    X = []
    Y = []
    for batch in iterate_minibatches(prefix, audio_paths_list, config['CNN']['batch_size']):      
        # feature_maps[i][j, k, l, m]
        # i: layer where extracted the feature
        # j: batch-sample dimension
        # k: one feature-map axis
        # l: other feature-map axis
        # m: feature-map
        feature_maps = sess.run(features_definition, feed_dict={x: batch[0], is_train: config['CNN']['is_train']})
        for j in range(config['CNN']['batch_size']): # for every song in a batch
            tmp_features = np.zeros((len(feature_maps),feature_maps[0].shape[3]))
            for i in range(len(feature_maps)): # for every layer where feature are extracted
                for m in range(feature_maps[i].shape[3]): # for every feature-map
                    tmp_features[i, m] = np.mean(np.squeeze(feature_maps[i][j, :, :, m]))
            X.append(tmp_features)
            Y.append(batch[1][j]) 
        print(Y)
        print(np.array(X).shape)
    
    return X, Y


def compute_spectrogram(audio_path, sampling_rate):
    # compute spectrogram
    audio, sr = librosa.load(audio_path, sr=sampling_rate)
    audio_rep = librosa.feature.melspectrogram(y=audio,
                                               sr=sampling_rate,
                                               hop_length=256,
                                               n_fft=512,
                                               n_mels=config['CNN']['n_mels'],
                                               power=2,
                                               fmin=0.0,
                                               fmax=6000.0).T

    # normalize audio representation
    # audio_rep = np.log10(10000 * audio_rep + 1)
    # audio_rep = (audio_rep - config['patches_params']['mean']) / config['patches_params']['std']
    audio_rep = librosa.core.logamplitude(audio_rep)
    audio_rep = np.expand_dims(audio_rep, axis=0)
    audio_rep = audio_rep[:, :config['CNN']['n_frames'], :]
    return audio_rep


def model():
    with tf.name_scope('model'):
        global x
        x = tf.placeholder(tf.float32, [None, None, config['CNN']['n_mels']])

        global is_train
        is_train = tf.placeholder(tf.bool)

        print('Input: ' + str(x.get_shape))

        bn_x = tf.layers.batch_normalization(x, training=is_train)
        input_layer = tf.reshape(bn_x,
                                 [-1, config['CNN']['n_frames'], config['CNN']['n_mels'], 1])
        conv1 = tf.layers.conv2d(inputs=input_layer,
                                 filters=32,
                                 kernel_size=[3, 3],
                                 padding='valid',
                                 activation=tf.nn.elu,
                                 name='1CNN',
                                 kernel_initializer=tf.contrib.layers.variance_scaling_initializer())
        bn_conv1 = tf.layers.batch_normalization(conv1, training=is_train)
        pool1 = tf.layers.max_pooling2d(inputs=bn_conv1, pool_size=[4, 2], strides=[4, 2])

        conv2 = tf.layers.conv2d(inputs=pool1,
                                 filters=32,
                                 kernel_size=[3, 3],
                                 padding='valid',
                                 activation=tf.nn.elu,
                                 name='2CNN',
                                 kernel_initializer=tf.contrib.layers.variance_scaling_initializer())
        bn_conv2 = tf.layers.batch_normalization(conv2, training=is_train)
        pool2 = tf.layers.max_pooling2d(inputs=bn_conv2, pool_size=[4, 3], strides=[4, 3])

        conv3 = tf.layers.conv2d(inputs=pool2,
                                 filters=32,
                                 kernel_size=[3, 3],
                                 padding='valid',
                                 activation=tf.nn.elu,
                                 name='3CNN',
                                 kernel_initializer=tf.contrib.layers.variance_scaling_initializer())
        bn_conv3 = tf.layers.batch_normalization(conv3, training=is_train)
        pool3 = tf.layers.max_pooling2d(inputs=bn_conv3, pool_size=[5, 1], strides=[5, 1])

        conv4 = tf.layers.conv2d(inputs=pool3,
                                 filters=32,
                                 kernel_size=[3, 3],
                                 padding='valid',
                                 activation=tf.nn.elu,
                                 name='4CNN',
                                 kernel_initializer=tf.contrib.layers.variance_scaling_initializer())
        bn_conv4 = tf.layers.batch_normalization(conv4, training=is_train)
        pool4 = tf.layers.max_pooling2d(inputs=bn_conv4, pool_size=[4, 3], strides=[4, 3])

        conv5 = tf.layers.conv2d(inputs=pool4, filters=32, kernel_size=[3, 3], padding='valid', activation=tf.nn.elu,
                                 name='5CNN', kernel_initializer=tf.contrib.layers.variance_scaling_initializer())

    global sess
    sess = tf.InteractiveSession()
    sess.run(tf.global_variables_initializer())

    return [conv1, conv2, conv3, conv4, conv5]


def select_cnn_feature_layers(feature_maps, selected_features_list):
    selected_features = []
    for i in range(len(feature_maps)):
        tmp = np.array([])
        for j in selected_features_list:
            tmp = np.concatenate((tmp, np.squeeze(feature_maps[i][j])))
        selected_features.append(tmp)
    return selected_features


# GTZAN

def gtzan_ground_truth(ground_truth):

    if ground_truth == 'blues':
        return 0
    elif ground_truth == 'classical':
        return 1
    elif ground_truth == 'country':
        return 2
    elif ground_truth == 'disco':
        return 3
    elif ground_truth == 'hiphop':
        return 4
    elif ground_truth == 'jazz':
        return 5
    elif ground_truth == 'metal':
        return 6
    elif ground_truth == 'pop':
        return 7
    elif ground_truth == 'reggae':
        return 8
    elif ground_truth == 'rock':
        return 9
    else:
        print('Warning: did not find the corresponding ground truth (' + str(ground_truth) + ').')
        import ipdb; ipdb.set_trace()


# MFCCs

def extract_mfcc_features(audio, sampling_rate=12000): # as in https://github.com/keunwoochoi/transfer_learning_music/
    src_zeros = np.zeros(1024) # min length to have 3-frame mfcc's
    src, sr = librosa.load(audio, sr=sampling_rate, duration=29.) # max len: 29s, can be shorter.
    if len(src) < 1024:
        print('Warning: audio is too short and the code is zero-padding for you!')
        src_zeros[:len(src)] = src
        src = src_zeros
    
    mfcc = librosa.feature.mfcc(src, sampling_rate, n_mfcc=20)
    dmfcc = mfcc[:, 1:] - mfcc[:, :-1]
    ddmfcc = dmfcc[:, 1:] - dmfcc[:, :-1]
    return np.concatenate((np.mean(mfcc, axis=1), np.std(mfcc, axis=1),
                           np.mean(dmfcc, axis=1), np.std(dmfcc, axis=1),
                           np.mean(ddmfcc, axis=1), np.std(ddmfcc, axis=1)), 
                           axis=0)


def format_mfcc_data(prefix, list_audios):
    songs_list = open(list_audios, 'r')
    X = []
    Y = []
    n_song = 0
    for song in songs_list:
        ground_truth = song[:song.rfind('/')]
        print(str(n_song) + ': ' + song[:-1])
        X.append(extract_mfcc_features(prefix + song[:-1], config['sampling_rate']))
        Y.append(gtzan_ground_truth(ground_truth))
        n_song += 1
        print(Y)
        print(np.array(X).shape)
    return X, Y


if __name__ == '__main__':

    #--------------------#
    # FEATURE EXTRACTION #
    #--------------------#
    
    print(config)

    if not config['load_extracted_features']: 

        features_path = str(config['experiment_name']) + '_' + str(int(time.time()))

        print('Extracting features..')

        if config['features_type'] == 'CNN':
            features_definition = model()
            x, y = format_cnn_data(prefix=config['audio_path'],
                                    list_audios=config['audios_list'])

        elif config['features_type'] == 'MFCC':
            x, y = format_mfcc_data(prefix=config['audio_path'],
                                    list_audios=config['audios_list'])


        print('Storing extracted features..')        

        if not os.path.exists(config['save_extracted_features_folder']):
            os.makedirs(config['save_extracted_features_folder'])

        with open(config['save_extracted_features_folder'] + features_path + '.pkl', 'wb') as f:
            pickle.dump([x, y, config], f)

    else:  # load extracted features
        
        print('Loading features: ' + config['load_extracted_features'])

        with open(config['load_extracted_features'], 'rb') as f:
            x, y, config = pickle.load(f)


    if config['features_type'] == 'CNN':
        print('Select CNN features..')
        x = select_cnn_feature_layers(x, config['CNN']['selected_features_list'])

    print(np.array(x).shape)

    #------------#
    # CLASSIFIER #
    #------------#

    svc = SVC()
    svm_hps = GridSearchCV(svc, svm_params, cv=2, n_jobs=3, pre_dispatch=3*8).fit(x, y)
    print('Best score of {}: {}'.format(svm_hps.best_score_,svm_hps.best_params_))
    print(svm_hps.best_score_)
    print(config)

# NOTES ON SPECTROGRAM - Mel power spectrogram. Sampling rate: 12k. fmin=0 and fmax=6000. Using shorter clips.
