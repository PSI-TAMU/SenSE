import os
import glob
import pickle
import ledapy
import tqdm
import argparse
import pandas as pd
import numpy as np
import seaborn as sns
import neurokit2 as nk
import matplotlib.pyplot as plt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Preprocess the data')
    parser.add_argument('-s', '--subject_id', help='Subject ID')
    parser.add_argument('--data_path', default='../dataset/processed', help='Path to the data')
    parser.add_argument('--output_path', default='./data', help='Path to save the extracted data')
    args = parser.parse_args()

    data_root = os.path.join(args.data_path, args.subject_id)
    assert os.path.exists(data_root), f"Data path {data_root} does not exist"

    output_root = os.path.join(args.output_path, args.subject_id)
    os.makedirs(output_root, exist_ok=True)

    # Load the data
    data_paths = sorted(glob.glob(os.path.join(data_root, '*.pkl')), key=lambda x: int(x.split('/')[-1].split('.')[0]))
    
    extracted_ecg = None
    extracted_ppg = None
    extracted_eda = None
    for data_path in tqdm.tqdm(data_paths):
        cgm_data = pd.read_pickle(data_path)
        cgm_idx = cgm_data['Index']
        cgm_timestamp = cgm_data['Timestamp']
        cgm_glucose = cgm_data['glucose']

        if cgm_glucose < 40 or cgm_glucose > 180:
            continue

        # ecg data
        ecg_data = cgm_data['zephyr']['ECG']
        summary_data = cgm_data['zephyr']['Summary']

        ecg_fs = 250
        ecg_clean = nk.ecg_clean(ecg_data['EcgWaveform'], sampling_rate=ecg_fs)

        try:
            _, rpeaks = nk.ecg_peaks(ecg_clean, sampling_rate=ecg_fs, correct_artifacts=True)
            r_peaks = np.unique(rpeaks['ECG_R_Peaks'])

            window_size = 3 * ecg_fs
            _extracted_ecg = []
            for peak in r_peaks:
                start_idx = peak - window_size//2
                end_idx = start_idx + window_size
                try:
                    start_t = ecg_data['Time'][start_idx]
                    end_t = ecg_data['Time'][end_idx]
                    beat_ecg = ecg_clean[start_idx:end_idx]

                    if beat_ecg.shape[0] == 0:
                        continue
                    
                    summary_window = (summary_data['Time'] >= start_t) & (summary_data['Time'] < end_t)
                    avg_HRConfidence = summary_data["HRConfidence"][summary_window].mean()
                    avg_ECGNoise = summary_data["ECGNoise"][summary_window].mean()

                    _extracted_ecg.append({
                        'ecg': beat_ecg,
                        'start_t': start_t,
                        'end_t': end_t,
                        'glucose': cgm_glucose,
                        'CGM_idx': cgm_idx,
                        'Timestamp': cgm_timestamp,
                        'HRConfidence': avg_HRConfidence,
                        'ECGNoise': avg_ECGNoise
                    })
                except:
                    pass
            
            _extracted_ecg = pd.DataFrame(_extracted_ecg)
            if _extracted_ecg.shape[0] != 0:
                clean_extracted_ecg = _extracted_ecg[(_extracted_ecg['HRConfidence'] >= 100) & (_extracted_ecg['ECGNoise'] <= 0.001)]
                if clean_extracted_ecg.shape[0] != 0:
                    clean_extracted_ecg = clean_extracted_ecg.sort_values('start_t')
                    extracted_ecg = pd.concat([extracted_ecg, clean_extracted_ecg], axis=0) if extracted_ecg is not None else clean_extracted_ecg
        except Exception as e:
            print(e)
            pass
        
        # ppg data
        try:
            ppg_data = cgm_data['e4']['BVP']
            ppg_fs = 64
            ppg_clean = nk.ppg_clean(ppg_data['BVP'], sampling_rate=ppg_fs)
        
            window_size = 30 * ppg_fs
            overlap_ratio = 0.5

            _extracted_ppg = []
            for i in range(0, ppg_data['Time'].shape[0], int(window_size * overlap_ratio)):
                try:
                    start_idx = i
                    end_idx = start_idx + window_size
                    start_t = ppg_data['Time'][start_idx]
                    end_t = ppg_data['Time'][end_idx]
                    window_ppg = ppg_clean[start_idx:end_idx]

                    _extracted_ppg.append({
                        'ppg': window_ppg,
                        'start_t': start_t,
                        'end_t': end_t,
                        'glucose': cgm_glucose,
                        'CGM_idx': cgm_idx,
                        'Timestamp': cgm_timestamp,
                    })
                except:
                    pass
            _extracted_ppg = pd.DataFrame(_extracted_ppg)
            extracted_ppg = pd.concat([extracted_ppg, _extracted_ppg], axis=0) if extracted_ppg is not None else _extracted_ppg
        except Exception as e:
            print(e)
            pass


        # eda data
        eda_data = cgm_data['e4']['EDA']
        eda_fs = 4
        try:
            phasicdata = ledapy.runner.getResult(eda_data['EDA'], 'phasicdata', eda_fs)
            tonicdata = eda_data['EDA'] - phasicdata

            _extracted_eda = [{
                'phasic': phasicdata,
                'tonic': tonicdata,
                'start_t': eda_data['Time'][0],
                'end_t': eda_data['Time'][-1],
                'glucose': cgm_glucose,
                'CGM_idx': cgm_idx,
                'Timestamp': cgm_timestamp,
            }]
            _extracted_eda = pd.DataFrame(_extracted_eda)
            extracted_eda = pd.concat([extracted_eda, _extracted_eda], axis=0) if extracted_eda is not None else _extracted_eda
        except Exception as e:
            print(e)
            pass

    # Save the extracted data
    extracted_ecg.to_pickle(os.path.join(output_root, 'ecg.pkl'))
    extracted_ppg.to_pickle(os.path.join(output_root, 'ppg.pkl'))
    extracted_eda.to_pickle(os.path.join(output_root, 'eda.pkl'))