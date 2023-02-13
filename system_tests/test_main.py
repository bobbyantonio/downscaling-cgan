import sys, os
import unittest
import tempfile
import yaml
from pathlib import Path
from glob import glob

HOME = Path(__file__).parents[1]
sys.path.append(str(HOME))

from dsrnngan.main import main, parser
from dsrnngan import utils


class TestMain(unittest.TestCase):
    
    def test_main_ifs_nimrod(self):

        config_path = str(HOME / 'system_tests' / 'data' / 'config-test.yaml')
        with open(config_path, 'r') as f:
            setup_params = yaml.safe_load(f)
        
        log_folder = str(HOME / 'system_tests' / 'data' / 'tmp')
        setup_params['SETUP']['log_folder'] = log_folder
        if not os.path.isdir(log_folder):
            os.mkdir(log_folder)
            
        args = parser.parse_args(['--config', config_path])
        
        data_paths = {'TFRecords': {'tfrecords_path': str(HOME / 'data/tfrecords')}}
        df_dict = {'downscaling_factor': 10, 'steps': [5, 2]}
        
        # Remove constants
        setup_params['DATA'] = {
            'fcst_data_source': 'ifs',
            'obs_data_source': 'nimrod',
            'input_channels': 9,
            'fcst_image_width': 20, # Assumes a square image
            'output_image_width': 200,
            'constants_width': 200,
            'constant_fields': 2,
            'load_constants': True
        }
        
        main(restart=args.restart, do_training=args.do_training, 
                evalnum=args.evalnum, qual=args.qual,
                rank=args.rank, 
                plot_ranks=args.plot_ranks,
                setup_params=setup_params,
                data_paths=data_paths)
        
    def test_main_era5_imerg(self):
        
        config_path = str(HOME / 'system_tests' / 'data' / 'config-test.yaml')
        with open(config_path, 'r') as f:
            setup_params = yaml.safe_load(f)
        log_folder = str(HOME / 'system_tests' / 'data' / 'tmp')
        if not os.path.isdir(log_folder):
            os.mkdir(log_folder)

        setup_params['SETUP']['log_folder'] = log_folder
            
        args = parser.parse_args(['--evaluate'])
        
        records_folder = '/user/work/uz22147/tfrecords/era5_imerg_random_bins'
        data_paths = {'TFRecords': {'tfrecords_path': records_folder}}
        
        setup_params['DOWNSCALING'] = {'downscaling_factor': 1, 'steps': [1]}
        
        setup_params['EVAL']['num_batches'] = 2
        
        # Remove constants
        setup_params['DATA'] = {
            'fcst_data_source': 'era5',
            'obs_data_source': 'imerg',
            'input_channels': 5,
            'input_image_width': 200, # Assumes a square image
            'constant_fields': 1,
            'log_precip': True,
            'fcst_norm': True,
            'min_latitude': -11.95,
            'max_latitude': 15.05,
            'latitude_step_size': 0.1,
            'min_longitude': 25.05,
            'max_longitude': 51.45,
            'longitude_step_size': 0.1
        }
        
        # Save config to tfrecords folder 
        utils.write_to_yaml(os.path.join(records_folder, 'local_config.yaml'), setup_params)
        utils.write_to_yaml(os.path.join(records_folder, 'data_paths.yaml'), data_paths)
        
        # Try with qual
        main(restart=args.restart, do_training=args.do_training, 
            evalnum=args.evalnum, evaluate=True,
            plot_ranks=args.plot_ranks,
            records_folder=records_folder,
            noise_factor=args.noise_factor,
            num_images=args.num_images,
            ensemble_size=args.ensemble_size)
        
        # Check that logs written to folder
        self.assertTrue(os.path.isfile(os.path.join(log_folder, 'eval.txt')))


if __name__ == '__main__':
    unittest.main()