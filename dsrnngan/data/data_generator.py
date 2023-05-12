""" Data generator class for full-image evaluation of precipitation downscaling network """
import random
import numpy as np
import tensorflow as tf
from typing import Union, Iterable
from tensorflow.keras.utils import Sequence

from dsrnngan.data.data import load_fcst_radar_batch, load_hires_constants, all_fcst_hours, DATA_PATHS, all_ifs_fields, all_era5_fields
from dsrnngan.utils import read_config

fields_lookup = {'ifs': all_ifs_fields, 'era5': all_era5_fields}

class DataGenerator(Sequence):
    def __init__(self, dates: list, batch_size: int, forecast_data_source: str, observational_data_source: str, data_paths: dict=DATA_PATHS,
                 shuffle: bool=True, constants: bool=True, hour: Union[int, str]='random', longitude_range: Iterable[float]=None,
                 latitude_range: Iterable[float]=None, normalise: bool=True,
                 downsample: bool=False, seed: int=None):
        
        if seed is not None:
            random.seed(seed)
        self.dates = dates

        if isinstance(hour, str):
            if hour == 'random':
                self.hours = np.repeat(all_fcst_hours, len(self.dates))
                self.dates = np.tile(self.dates, len(all_fcst_hours))
            else:
                assert False, f"Unsupported hour {hour}"

        elif isinstance(hour, (int, np.integer)):
            self.hours = np.repeat(hour, len(self.dates))
            self.dates = np.tile(self.dates, 1)  # lol

        elif isinstance(hour, (list, np.ndarray)):
            self.hours = np.repeat(hour, len(self.dates))
            self.dates = np.tile(self.dates, len(hour))

            if forecast_data_source == 'era5':
                raise ValueError('ERA5 data only supports daily')

        else:
            raise ValueError(f"Unsupported hour {hour}")
    

        self.shuffle = shuffle
        if self.shuffle:
            np.random.seed(seed)
            self.shuffle_data()

        self.forecast_data_source = forecast_data_source
        self.observational_data_source = observational_data_source
        self.data_paths = data_paths
        self.batch_size = batch_size

        self.fcst_fields = fields_lookup[self.forecast_data_source.lower()]
        self.shuffle = shuffle
        self.hour = hour
        self.normalise = normalise
        self.downsample = downsample
        self.latitude_range = latitude_range
        self.longitude_range = longitude_range
        
        self.permute_var = None
            
        # if permute_fcst_index is not None:
        #     if permute_fcst_index > len(self.fcst_fields):
        #         raise ValueError(f'permute_fcst_index must be between 0 and {len(self.fcst_fields)}')
        #     self.permute_var = self.fcst_fields[permute_fcst_index]
        #     random.seed(seed)
        #     permuted_indexes = random.sample(list(range(len(dates))), len(dates))
            
        #     self.permuted_dates = self.dates[permuted_indexes]
        #     self.permuted_hours = self.hours[permuted_indexes]
               
        if self.downsample:
            # read downscaling factor from file
            self.ds_factor = read_config.read_config()['DOWNSCALING']["downscaling_factor"]
        
        if not constants:
            # Dummy constants
            self.constants = np.ones((self.batch_size, len(self.latitude_range), len(self.longitude_range), 1))
        elif constants is True:
            self.constants = load_hires_constants(self.batch_size,
                                                  lsm_path=data_paths['GENERAL']['LSM'], 
                                                  oro_path=data_paths['GENERAL']['OROGRAPHY'],
                                                  latitude_vals=latitude_range, longitude_vals=longitude_range)
        else:
            self.constants = np.repeat(constants, self.batch_size, axis=0)

    def __len__(self):
        # Number of batches in dataset
        return len(self.dates) // self.batch_size

    def _dataset_downsampler(self, radar):
        kernel_tf = tf.constant(1.0/(self.ds_factor*self.ds_factor), shape=(self.ds_factor, self.ds_factor, 1, 1), dtype=tf.float32)
        image = tf.nn.conv2d(radar, filters=kernel_tf, strides=[1, self.ds_factor, self.ds_factor, 1], padding='VALID',
                             name='conv_debug', data_format='NHWC')
        return image

    def __getitem__(self, idx):
        # Get batch at index idx
        dates_batch = self.dates[idx*self.batch_size:(idx+1)*self.batch_size]
        hours_batch = self.hours[idx*self.batch_size:(idx+1)*self.batch_size]

        # Load and return this batch of images
        data_x_batch, data_y_batch = load_fcst_radar_batch(
            dates_batch,
            fcst_dir=self.data_paths['GENERAL'][self.forecast_data_source.upper()],
            obs_data_dir=self.data_paths['GENERAL'][self.observational_data_source.upper()],
            constants_dir=self.data_paths['GENERAL']['CONSTANTS'],
            fcst_fields=self.fcst_fields,
            fcst_data_source=self.forecast_data_source,
            obs_data_source=self.observational_data_source,
            hour=hours_batch,
            norm=self.normalise,
            latitude_range=self.latitude_range,
            longitude_range=self.longitude_range)
        
        # if self.permute_var is not None:
        #     data_x_batch, data_y_batch = load_fcst_radar_batch(
        #         dates_batch,
        #         fcst_dir=self.data_paths['GENERAL'][self.forecast_data_source.upper()],
        #         obs_data_dir=self.data_paths['GENERAL'][self.observational_data_source.upper()],
        #         constants_dir=self.data_paths['GENERAL']['CONSTANTS'],
        #         fcst_fields=[self.permute_var],
        #         fcst_data_source=self.forecast_data_source,
        #         obs_data_source=None,
        #         hour=hours_batch,
        #         norm=self.normalise,
        #         latitude_range=self.latitude_range,
        #         longitude_range=self.longitude_range)
        
        if self.downsample:
            # replace forecast data by coarsened radar data!
            data_x_batch = self._dataset_downsampler(data_y_batch[..., np.newaxis])


        return {"lo_res_inputs": data_x_batch,
                "hi_res_inputs": self.constants,
                "dates": dates_batch, "hours": hours_batch},\
                {"output": data_y_batch}


    def shuffle_data(self):
        assert len(self.hours) == len(self.dates)
        p = np.random.permutation(len(self.hours))
        self.hours = self.hours[p]
        self.dates = self.dates[p]
        return

    def on_epoch_end(self):
        if self.shuffle:
            self.shuffle_data()

class PermutedDataGenerator(Sequence):
    """
    A class designed to mimic the data generator, but returning values where the inputs have been permuted
    
    Designed to be used in a situation where data has already been gather
    """
    def __init__(self, lo_res_inputs: np.ndarray, hi_res_inputs: np.ndarray, outputs: np.ndarray, dates: np.ndarray, hours: np.ndarray,
                 permute_fcst_index: int, seed: int=None):
            
            self.lo_res_inputs = lo_res_inputs
            self.hi_res_inputs = hi_res_inputs
            self.outputs = outputs
            self.dates = dates
            self.hours = hours
            
            num_forecast_vars = self.lo_res_inputs.shape[-1]
            if permute_fcst_index > num_forecast_vars:
                raise ValueError(f'permute_fcst_index must be between 0 and {num_forecast_vars}')
            self.permute_fcst_index = permute_fcst_index
            
            random.seed(seed)
            self.permuted_indexes = random.sample(list(range(len(self.dates))), len(self.dates))

    def __getitem__(self, idx):

        permuted_lo_res_inputs = self.lo_res_inputs.copy()
        permuted_lo_res_inputs[:,:,:,self.permute_fcst_index] = permuted_lo_res_inputs[self.permuted_indexes, :, :, self.permute_fcst_index]
        
        return {"lo_res_inputs": permuted_lo_res_inputs[idx:idx+1, :, :, :],
                "hi_res_inputs": self.hi_res_inputs[idx, :, :, :],
                "dates": self.dates[idx,:], "hours": self.hours[idx, :]},\
                {"output": self.outputs}
                
if __name__ == "__main__":
    pass