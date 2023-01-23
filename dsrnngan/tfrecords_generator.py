import os
import glob
import datetime
import random
import time
import numpy as np
import tensorflow as tf
import logging
import hashlib
from argparse import ArgumentParser
from calendar import monthrange
from tqdm import tqdm
import pandas as pd
import git

from dsrnngan import read_config
from dsrnngan.data import file_exists
from dsrnngan.utils import hash_dict, write_to_yaml, date_range_from_year_month_range

logger = logging.getLogger(__file__)
logger.setLevel(logging.DEBUG)

return_dic = True

DATA_PATHS = read_config.get_data_paths()
records_folder = DATA_PATHS["TFRecords"]["tfrecords_path"]
ds_fac = read_config.read_config()['DOWNSCALING']["downscaling_factor"]

def DataGenerator(data_label, batch_size, fcst_shape, con_shape, 
                  out_shape, repeat=True, 
                  downsample=False, weights=None, 
                  records_folder=records_folder, seed=None):
    return create_mixed_dataset(data_label, 
                                batch_size,
                                fcst_shape,
                                con_shape,
                                out_shape,
                                repeat=repeat, 
                                downsample=downsample, 
                                weights=weights, 
                                folder=records_folder, 
                                seed=seed)


def create_mixed_dataset(data_label: str,
                         batch_size: int,
                         fcst_shape: tuple[int, int, int]=(20, 20, 9),
                         con_shape: tuple[int, int, int]=(200, 200, 2),
                         out_shape: tuple[int, int, int]=(200, 200, 1),
                         repeat: bool=True,
                         downsample: bool=False,
                         folder: str=records_folder,
                         shuffle_size: int=1024,
                         weights: list=None,
                         seed: int=None):
    """_summary_

    Args:
        year (int): year of data
        batch_size (int): size of batches
        fcst_shape (tuple[int, int, int], optional): shape of forecast input. Defaults to (20, 20, 9).
        con_shape (tuple[int, int, int], optional): shape of constants input. Defaults to (200, 200, 2).
        out_shape (tuple[int, int, int], optional): shape of output. Defaults to (200, 200, 1).
        repeat (bool, optional): repeat dataset or not. Defaults to True.
        downsample (bool, optional): whether to downsample or not. Defaults to False.
        folder (str, optional): folder containing tf records. Defaults to records_folder.
        shuffle_size (int, optional): buffer size of shuffling. Defaults to 1024.
        weights (list, optional): list of floats, weights of classes when sampling. Defaults to None.
        seed (int, optional): seed for shuffling and sampling. Defaults to None.

    Returns:
        _type_: _description_
    """    

    classes = 4
    if weights is None:
        weights = [1./classes]*classes
    datasets = [create_dataset(data_label,
                               i,
                               fcst_shape=fcst_shape,
                               con_shape=con_shape,
                               out_shape=out_shape,
                               folder=folder,
                               shuffle_size=shuffle_size,
                               repeat=repeat,
                               seed=seed)
                for i in range(classes)]
    
    sampled_ds = tf.data.Dataset.sample_from_datasets(datasets,
                                                      weights=weights, seed=seed).batch(batch_size)

    if downsample and return_dic:
        sampled_ds = sampled_ds.map(_dataset_downsampler)
    elif downsample and not return_dic:
        sampled_ds = sampled_ds.map(_dataset_downsampler_list)
    sampled_ds = sampled_ds.prefetch(2)
    return sampled_ds

# Note, if we wanted fewer classes, we can use glob syntax to grab multiple classes as once
# e.g. create_dataset(2015,"[67]")
# will take classes 6 & 7 together

def _dataset_downsampler(inputs, outputs):
    image = outputs['output']
    kernel_tf = tf.constant(1.0/(ds_fac*ds_fac), shape=(ds_fac, ds_fac, 1, 1), dtype=tf.float32)
    image = tf.nn.conv2d(image, filters=kernel_tf, strides=[1, ds_fac, ds_fac, 1], padding='VALID',
                         name='conv_debug', data_format='NHWC')
    inputs['lo_res_inputs'] = image
    return inputs, outputs


def _dataset_downsampler_list(inputs, constants, outputs):
    image = outputs
    kernel_tf = tf.constant(1.0/(ds_fac*ds_fac), shape=(ds_fac, ds_fac, 1, 1), dtype=tf.float32)
    image = tf.nn.conv2d(image, filters=kernel_tf, strides=[1, ds_fac, ds_fac, 1], padding='VALID', name='conv_debug', data_format='NHWC')
    inputs = image
    return inputs, constants, outputs


def _parse_batch(record_batch,
                 insize=(20, 20, 9),
                 consize=(200, 200, 2),
                 outsize=(200, 200, 1)):
    """_summary_

    Args:
        record_batch (tf.python.framework.ops.EagerTensor): Single item from a tf Records Dataset
        insize (tuple, optional): shape of the forecast data (lat, lon, n_features). Defaults to (20, 20, 9).
        consize (tuple, optional): shape of the constants data (lat, lon, n_features). Defaults to (200, 200, 2).
        outsize (tuple, optional): shape of the output (lat, lon, n_features). Defaults to (200, 200, 1).

    Returns:
        tuple: tuple of dicts, containing inputs and outputs
    """
    # Create a description of the features
    

    feature_description = {
        'generator_input': tf.io.FixedLenFeature(insize, tf.float32),
        'constants': tf.io.FixedLenFeature(consize, tf.float32),
        'generator_output': tf.io.FixedLenFeature(outsize, tf.float32),
    }

    # Parse the input `tf.Example` proto using the dictionary above
    example = tf.io.parse_example(record_batch, feature_description)
    
    if return_dic:
        output = ({'lo_res_inputs': example['generator_input'],
                   'hi_res_inputs': example['constants']},
                  {'output': example['generator_output']})

        return output
    else:
        return example['generator_input'], example['constants'], example['generator_output']


def create_dataset(data_label: str,
                   clss: str,
                   fcst_shape=(20, 20, 9),
                   con_shape=(200, 200, 2),
                   out_shape=(200, 200, 1),
                   folder: str=records_folder,
                   shuffle_size: int=1024,
                   repeat=True,
                   seed: int=None):
    """
    Load tfrecords and parse into appropriate shapes

    Args:
        year (int): year
        clss (str): class (bin to take data from)
        fcst_shape (tuple, optional): shape of the forecast data (lat, lon, n_features). Defaults to (20, 20, 9).
        con_shape (tuple, optional): shape of the constants data (lat, lon, n_features). Defaults to (200, 200, 2).
        out_shape (tuple, optional): shape of the output (lat, lon, n_features). Defaults to (200, 200, 1).
        folder (_type_, optional): folder containing tf records. Defaults to records_folder.
        shuffle_size (int, optional): buffer size for shuffling. Defaults to 1024.
        repeat (bool, optional): create repeat dataset or not. Defaults to True.

    Returns:
        tf.data.DataSet: _description_
    """
    # Use autotune to tune the prefetching of records in parrallel to processing to improve performance
    AUTOTUNE = tf.data.experimental.AUTOTUNE

    fl = glob.glob(f"{folder}/{data_label}_*.{clss}.tfrecords")
    
    ds = tf.data.TFRecordDataset(fl,
                                 num_parallel_reads=AUTOTUNE)
    
    ds = ds.shuffle(shuffle_size, seed=seed)

    ds = ds.map(lambda x: _parse_batch(x,
                                       insize=fcst_shape,
                                       consize=con_shape,
                                       outsize=out_shape))
    if repeat:
        return ds.repeat()
    else:
        return ds


def create_fixed_dataset(year=None,
                         mode='validation',
                         batch_size=16,
                         downsample=False,
                         fcst_shape=(20, 20, 9),
                         con_shape=(200, 200, 2),
                         out_shape=(200, 200, 1),
                         name=None,
                         folder=records_folder):
    assert year is not None or name is not None, "Must specify year or file name"
    if name is None:
        name = os.path.join(folder, f"{mode}{year}.tfrecords")
    else:
        name = os.path.join(folder, name)
    fl = glob.glob(name)
    files_ds = tf.data.Dataset.list_files(fl)
    ds = tf.data.TFRecordDataset(files_ds,
                                 num_parallel_reads=1)
    ds = ds.map(lambda x: _parse_batch(x,
                                       insize=fcst_shape,
                                       consize=con_shape,
                                       outsize=out_shape))
    ds = ds.batch(batch_size)
    if downsample and return_dic:
        ds = ds.map(_dataset_downsampler)
    elif downsample and not return_dic:
        ds = ds.map(_dataset_downsampler_list)
    return ds


def _float_feature(list_of_floats):  # float32
    return tf.train.Feature(float_list=tf.train.FloatList(value=list_of_floats))

def write_data(year_month_range,
               data_label,
               forecast_data_source, 
               observational_data_source,
               hours,
               img_chunk_width=20,
               num_class=4,
               img_size = 94,
               scaling_factor = 10,
               log_precip=True,
               fcst_norm=True,
               data_paths=DATA_PATHS,
               constants=True,
               latitude_range=None,
               longitude_range=None,
               debug=False):

    from .data_generator import DataGenerator
    logger.info('Start of write data')
    logger.info(locals())     
      
    dates = date_range_from_year_month_range(year_month_range)
    start_date = dates[0]
    
    # This is super slow! So removing it for now, there are checls further on that deal with it
    # dates = [item for item in dates if file_exists(data_source=observational_data_source, year=item.year,
    #                                                     month=item.month, day=item.day,
    #                                                     data_paths=data_paths)]
    
    dates = [item for item in dates if file_exists(data_source=forecast_data_source, year=item.year,
                                                        month=item.month, day=item.day,
                                                        data_paths=data_paths)]
    if dates:
        if not dates[0] == start_date and not debug:
            # Means there likely isn't forecast data for the day before
            dates = dates[1:]
            
        records_folder = data_paths["TFRecords"]["tfrecords_path"]

        nsamples = (img_size // img_chunk_width)**2
        logger.info(f"Samples per image:{nsamples}")
        
        config = read_config.read_config()

        if not os.path.isdir(records_folder):
            os.mkdir(records_folder)
        
        #  Create directory that is hash of setup params, so that we know it's the right data later on
        hash_dir = os.path.join(records_folder, hash_dict(config))
        
        if not os.path.isdir(hash_dir):
            os.mkdir(hash_dir)
        
        print(f'Output folder will be {hash_dir}')
            
        # Write params in directory
        write_to_yaml(os.path.join(hash_dir, 'local_config.yaml'), config)
        write_to_yaml(os.path.join(hash_dir, 'data_paths.yaml'), data_paths)
        
        with open(os.path.join(hash_dir, 'git_commit.txt'), 'w+') as ofh:
            repo = git.Repo(search_parent_directories=True)
            sha = repo.head.object.hexsha
            ofh.write(sha)
        
        if debug:
            dates = dates[:1]

        for hour in hours:
            print('Hour = ', hour)
            start_time = time.time()
            dgc = DataGenerator(dates=[item.strftime('%Y%m%d') for item in dates],
                                forecast_data_source=forecast_data_source, 
                                observational_data_source=observational_data_source,
                                data_paths=data_paths,
                                batch_size=1,
                                log_precip=log_precip,
                                shuffle=False,
                                constants=constants,
                                hour=hour,
                                fcst_norm=fcst_norm,
                                longitude_range=longitude_range,
                                latitude_range=latitude_range)
            print(f'Data generator initialization took {time.time() - start_time}')
            
            start_time = time.time()
            fle_hdles = {}
            if dates:
                fle_hdles = []
                for fh in range(num_class):
                    flename = os.path.join(hash_dir, f"{data_label}_{hour}.{fh}.tfrecords")
                    fle_hdles.append(tf.io.TFRecordWriter(flename))
            
            print(f'File initialization took {time.time() - start_time}')
            print('starting fetching batches')
            for batch, date in tqdm(enumerate(dates), total=len(dates), position=0, leave=True):
                
                logger.debug(f"hour={hour}, batch={batch}")
                
                try:
                    
                    sample = dgc.__getitem__(batch)
                
                    # e.g. for image width 94 and img_chunk_width 20, can have 0:20 up to 74:94
                    #TODO: Try a different way of sampling, depending on size of nsamples.
                    # Or given nsamples is fixed, just choose all the possible indices?
                    
                    # valid_indices = list(range(0, img_size-img_chunk_width))   
                    # idx_selection = random.sample(valid_indices, nsamples)
                    # idy_selection = random.sample(valid_indices, nsamples)
                    
                    for k in range(sample[1]['output'].shape[0]):
                        for ii in range(nsamples):
                            idx = random.randint(0, img_size-img_chunk_width)
                            idy = random.randint(0, img_size-img_chunk_width)
                            # idx = idx_selection[ii]
                            # idy = idy_selection[ii]
                            
                            # TODO: Check that there is data and error if not throw error

                            observations = sample[1]['output'][k,
                                                        idx*scaling_factor:(idx+img_chunk_width)*scaling_factor,
                                                        idy*scaling_factor:(idy+img_chunk_width)*scaling_factor].flatten()

                            forecast = sample[0]['lo_res_inputs'][k,
                                                                idx:idx+img_chunk_width,
                                                                idy:idy+img_chunk_width,
                                                                :].flatten()
                            
                            const = sample[0]['hi_res_inputs'][k,
                                                                idx*scaling_factor:(idx+img_chunk_width)*scaling_factor,
                                                                idy*scaling_factor:(idy+img_chunk_width)*scaling_factor,
                                                                :].flatten()
                                
                            # Check no Null values
                            if np.isnan(observations).any() or np.isnan(forecast).any() or np.isnan(const).any():
                                raise ValueError('Unexpected NaN values in data')
                            
                            # Check for empty data
                            if forecast.sum() == 0 or const.sum() == 0:
                                raise ValueError('one or more of arrays is all zeros')
                            
                            # Check hi res data has same dimensions
                                
                            feature = {
                                'generator_input': _float_feature(forecast),
                                'constants': _float_feature(const),
                                'generator_output': _float_feature(observations)
                            }

                            features = tf.train.Features(feature=feature)
                            example = tf.train.Example(features=features)
                            example_to_string = example.SerializeToString()
                            
                            # Removing this for the moment while we figure out appropriate threshold
                            clss = random.choice(range(num_class))
                            # clss = min(int(np.floor(((observations > 0.1).mean()*num_class))), num_class-1)  # all class binning is here!

                            fle_hdles[clss].write(example_to_string)
                            
                            #TODO: write config to folder as well
                except FileNotFoundError as e:
                    print(f"Error loading hour={hour}, date={date}")
            
            for fh in fle_hdles:
                fh.close()
                    
        return hash_dir
    else:
        print('No dates found')

def write_train_test_data(*args, training_range,
                          validation_range=None,
                          test_range=None, **kwargs):
    
    
    write_data(training_range, *args,
               data_label='train', **kwargs)
    
    if validation_range:
        print('\n*** Writing validation data')
        write_data(validation_range, *args,
               data_label='validation', **kwargs)
        
    if test_range:
        print('\n*** Writing test data')

        write_data(test_range, *args,
                   data_label='test', **kwargs)


def save_dataset(tfrecords_dataset, flename, max_batches=None):

    assert return_dic, "Only works with return_dic=True"
    flename = os.path.join(records_folder, flename)
    fle_hdle = tf.io.TFRecordWriter(flename)
    for ii, sample in enumerate(tfrecords_dataset):
        logger.info(ii)
        if max_batches is not None:
            if ii == max_batches:
                break
        for k in range(sample[1]['output'].shape[0]):
            feature = {
                'generator_input': _float_feature(sample[0]['lo_res_inputs'][k, ...].numpy().flatten()),
                'constants': _float_feature(sample[0]['hi_res_inputs'][k, ...].numpy().flatten()),
                'generator_output': _float_feature(sample[1]['output'][k, ...].numpy().flatten())
            }
            features = tf.train.Features(feature=feature)
            example = tf.train.Example(features=features)
            example_to_string = example.SerializeToString()
            fle_hdle.write(example_to_string)
    fle_hdle.close()
    return


if __name__ == '__main__':
    
    parser = ArgumentParser(description='Write data to tf records.')

    parser.add_argument('--fcst-hours', nargs='+', default=np.arange(24), type=int, 
                    help='Hour(s) to process (space separated)')
    parser.add_argument('--records-folder', type=str, default=None)
    
    # Load relevant parameters from local config

    config = read_config.read_config()
    
    training_range = config['TRAIN']['training_range']
    val_range = config['VAL'].get('val_range')
    test_range = config.get('EVAL', {}).get('test_range')
    
    training_range = [str(item) for item in training_range]
    if val_range:
        val_range = [str(item) for item in val_range]
    if test_range:
        test_range = [str(item) for item in test_range]
    
    fcst_data_source = config['DATA']['fcst_data_source']
    obs_data_source = config['DATA']['obs_data_source']
    log_precip = config['DATA']['log_precip']
    fcst_norm = config['DATA'].get('fcst_norm', False)
    num_classes = config['DATA']['num_classes']
    img_size = config['DATA']['input_image_width']
    min_latitude = config['DATA']['min_latitude']
    max_latitude = config['DATA']['max_latitude']
    latitude_step_size = config['DATA']['latitude_step_size']
    min_longitude = config['DATA']['min_longitude']
    max_longitude = config['DATA']['max_longitude']
    longitude_step_size = config['DATA']['longitude_step_size']
    
    scaling_factor =  config['DOWNSCALING']['downscaling_factor']
    load_constants = config['DATA'].get('load_constants', True)
    img_chunk_width = config['TRAIN']['img_chunk_width']
    
    args = parser.parse_args()
    
    data_paths = DATA_PATHS
    if args.records_folder:
        data_paths['TFRecords']['tfrecords_path'] = args.records_folder
    
    write_train_test_data(training_range=training_range,
                          validation_range=val_range,
                          test_range=test_range,
                            forecast_data_source=fcst_data_source, 
                            observational_data_source=obs_data_source,
                            hours=args.fcst_hours,
                            img_chunk_width=img_chunk_width,
                            num_class=num_classes,
                            img_size=img_size,
                            scaling_factor=scaling_factor,
                            log_precip=log_precip,
                            fcst_norm=fcst_norm,
                            data_paths=data_paths,
                            constants=load_constants,
                            latitude_range=np.arange(min_latitude, max_latitude, latitude_step_size),
                            longitude_range=np.arange(min_longitude, max_longitude, longitude_step_size))
