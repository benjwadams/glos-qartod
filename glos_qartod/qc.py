#!/usr/bin/env python
'''
glider_qc/glider_qc.py
'''
import numpy as np
import numpy.ma as ma
import quantities as pq
import pandas as pd
from cf_units import Unit
from netCDF4 import num2date
from ioos_qartod.qc_tests import qc
from ioos_qartod.qc_tests import gliders as gliders_qc


class DatasetQC(object):
    def __init__(self, ncfile, config_file):
        self.ncfile = ncfile
        self.load_config(config_file)

    def find_geophysical_variables(self):
        '''
        Returns a list of variable names matching the geophysical variable's
        standard names for temperature, conductivity, density and salinity.
        '''
        variables = []
        valid_standard_names = [
            'sea_water_temperature',
            'sea_water_electrical_conductivity',
            'sea_water_density',
            'sea_water_pressure',
            'sea_water_practical_salinity'
        ]

        for standard_name in valid_standard_names:
            ncvar = self.ncfile.get_variables_by_attributes(standard_name=standard_name)
            if len(ncvar) == 1:
                variables.append(ncvar[0].name)
        return variables

    def find_ancillary_variables(self, ncvariable):
        '''
        Returns the valid ancillary variables associated with a particular
        variable.

        :param netCDF4.Variable ncvariable: Variable to get the ancillary
                                            variables for
        '''
        valid_variables = []
        ancillary_variables = getattr(ncvariable, 'ancillary_variables', '').split(' ')
        for varname in ancillary_variables:
            # Skip the standard GliderDAC
            if varname == '%s_qc' % ncvariable.name:
                continue
            if varname in self.ncfile.variables:
                valid_variables.append(varname)
        return valid_variables

    def append_ancillary_variable(self, parent, child):
        '''
        Links two variables through the ancillary_variables attribute

        :param netCDF.Variable parent: Parent Variable
        :param netCDF.Variable child: Status Flag Variable
        '''

        ancillary_variables = getattr(parent, 'ancillary_variables', '').split(' ')
        ancillary_variables.append(child.name)
        parent.ancillary_variables = ' '.join(ancillary_variables)

    def needs_qc(self, ncvariable):
        '''
        Returns True if the variable has no associated QC variables

        :param netCDF4.Variable ncvariable: Variable to get the ancillary
                                            variables for
        '''
        ancillary_variables = self.find_ancillary_variables(ncvariable)
        return len(ancillary_variables) == 0

    def create_qc_variables(self, ncvariable):
        '''
        Returns a list of variable names for the newly created variables for QC flags
        '''
        name = ncvariable.name
        standard_name = ncvariable.standard_name
        dims = ncvariable.dimensions

        templates = {
            'flat_line': {
                'name': 'qartod_%(name)s_flat_line_flag',
                'long_name': 'QARTOD Flat Line Test for %(standard_name)s',
                'standard_name': '%(standard_name)s status_flag',
                'flag_values': np.array([1, 2, 3, 4, 9], dtype=np.int8),
                'flag_meanings': 'GOOD NOT_EVALUATED SUSPECT BAD MISSING',
                'references': 'http://gliders.ioos.us/static/pdf/Manual-for-QC-of-Glider-Data_05_09_16.pdf',
                'qartod_test': 'flat_line'
            },
            'gross_range': {
                'name': 'qartod_%(name)s_gross_range_flag',
                'long_name': 'QARTOD Gross Range Test for %(standard_name)s',
                'standard_name': '%(standard_name)s status_flag',
                'flag_values': np.array([1, 2, 3, 4, 9], dtype=np.int8),
                'flag_meanings': 'GOOD NOT_EVALUATED SUSPECT BAD MISSING',
                'references': 'http://gliders.ioos.us/static/pdf/Manual-for-QC-of-Glider-Data_05_09_16.pdf',
                'qartod_test': 'gross_range'
            },
            'rate_of_change': {
                'name': 'qartod_%(name)s_rate_of_change_flag',
                'long_name': 'QARTOD Rate of Change Test for %(standard_name)s',
                'standard_name': '%(standard_name)s status_flag',
                'flag_values': np.array([1, 2, 3, 4, 9], dtype=np.int8),
                'flag_meanings': 'GOOD NOT_EVALUATED SUSPECT BAD MISSING',
                'references': 'http://gliders.ioos.us/static/pdf/Manual-for-QC-of-Glider-Data_05_09_16.pdf',
                'qartod_test': 'rate_of_change'
            },
            'spike': {
                'name': 'qartod_%(name)s_spike_flag',
                'long_name': 'QARTOD Spike Test for %(standard_name)s',
                'standard_name': '%(standard_name)s status_flag',
                'flag_values': np.array([1, 2, 3, 4, 9], dtype=np.int8),
                'flag_meanings': 'GOOD NOT_EVALUATED SUSPECT BAD MISSING',
                'references': 'http://gliders.ioos.us/static/pdf/Manual-for-QC-of-Glider-Data_05_09_16.pdf',
                'qartod_test': 'spike'
            },
            'pressure': {
                'name': 'qartod_monotonic_pressure_flag',
                'long_name': 'QARTOD Pressure Test for %(standard_name)s',
                'standard_name': '%(standard_name)s status_flag',
                'flag_values': np.array([1, 2, 3, 4, 9], dtype=np.int8),
                'flag_meanings': 'GOOD NOT_EVALUATED SUSPECT BAD MISSING',
                'references': 'http://gliders.ioos.us/static/pdf/Manual-for-QC-of-Glider-Data_05_09_16.pdf',
                'qartod_test': 'pressure'
            },
            'primary': {
                'name': 'qartod_%(name)s_primary_flag',
                'long_name': 'QARTOD Primary Flag for %(standard_name)s',
                'standard_name': '%(standard_name)s status_flag',
                'flag_values': np.array([1, 2, 3, 4, 9], dtype=np.int8),
                'flag_meanings': 'GOOD NOT_EVALUATED SUSPECT BAD MISSING',
                'references': 'http://gliders.ioos.us/static/pdf/Manual-for-QC-of-Glider-Data_05_09_16.pdf'
            }
        }

        qcvariables = []

        for tname, template in templates.items():
            if tname == 'pressure' and standard_name != 'sea_water_pressure':
                continue
            variable_name = template['name'] % {'name': name}

            if variable_name not in self.ncfile.variables:
                ncvar = self.ncfile.createVariable(variable_name, np.int8, dims, fill_value=np.int8(9))
            else:
                ncvar = self.ncfile.variables[variable_name]

            ncvar.units = '1'
            ncvar.standard_name = template['standard_name'] % {'standard_name': standard_name}
            ncvar.long_name = template['long_name'] % {'standard_name': standard_name}
            ncvar.flag_values = template['flag_values']
            ncvar.flag_meanings = template['flag_meanings']
            ncvar.references = template['references']
            if 'qartod_test' in template:
                ncvar.qartod_test = template['qartod_test']
            qcvariables.append(variable_name)
            self.append_ancillary_variable(ncvariable, ncvar)

        return qcvariables

    def load_config(self, path):
        '''
        Returns a dataframe loaded from the excel config file.
        '''
        df = pd.read_excel(path, header=1)
        return df

    @classmethod
    def normalize_variable(cls, values, units, standard_name):
        '''
        Returns an array of values that are converted into a standard set of
        units. The motivation behind this is so that we compare values of the
        same units when performing QC.
        '''
        mapping = {
            'sea_water_temperature': 'deg_C',
            'sea_water_electrical_conductivity': 'S m-1',
            'sea_water_salinity': '1',
            'sea_water_practical_salinity': 'S m-1',
            'sea_water_pressure': 'dbar',
            'sea_water_density': 'kg m-3'
        }
        converted = Unit(units).convert(values, mapping[standard_name])
        return converted

    def apply_qc(self, ncvariable):
        '''
        Applies QC to a qartod variable

        :param netCDF4.Variable ncvariable: A QARTOD Variable
        '''
        qc_tests = {
            'flat_line': qc.flat_line_check,
            'gross_range': qc.range_check,
            'rate_of_change': qc.rate_of_change_check,
            'spike': qc.spike_check,
            'pressure': gliders_qc.pressure_check
        }

        qartod_test = getattr(ncvariable, 'qartod_test', None)
        if not qartod_test:
            return
        standard_name = getattr(ncvariable, 'standard_name').split(' ')[0]
        parent = self.ncfile.get_variables_by_attributes(standard_name=standard_name)[0]
        test_params = self.config[standard_name][qartod_test]
        if 'thresh_val' in test_params:
            test_params['thresh_val'] = test_params['thresh_val'] / pq.hour

        times, values, mask = self.get_unmasked(parent)

        if qartod_test == 'rate_of_change':
            times = ma.getdata(times[~mask])
            dates = np.array(num2date(times, self.ncfile.variables['time'].units), dtype='datetime64[ms]')
            test_params['times'] = dates

        if qartod_test == 'pressure':
            test_params['pressure'] = values
        else:
            test_params['arr'] = values

        qc_flags = qc_tests[qartod_test](**test_params)
        ncvariable[~mask] = qc_flags

    def get_unmasked(self, ncvariable):
        times = self.ncfile.variables['time'][:]
        values = ncvariable[:]

        mask = np.zeros(times.shape[0], dtype=bool)

        if hasattr(values, 'mask'):
            mask |= values.mask

        if hasattr(times, 'mask'):
            mask |= times.mask

        values = ma.getdata(values[~mask])
        values = self.normalize_variable(values, ncvariable.units, ncvariable.standard_name)
        return times, values, mask

    def apply_primary_qc(self, ncvariable):
        '''
        Applies the primary QC array which is an aggregate of all the other QC
        tests.

        :param netCDF4.Variable ncvariable: NCVariable
        '''
        primary_qc_name = 'qartod_%s_primary_flag' % ncvariable.name
        if primary_qc_name not in self.ncfile.variables:
            return

        qcvar = self.ncfile.variables[primary_qc_name]

        ancillary_variables = self.find_ancillary_variables(ncvariable)
        vectors = []

        for qc_variable in ancillary_variables:
            ncvar = self.ncfile.variables[qc_variable]
            vectors.append(ma.getdata(ncvar[:]))

        flags = qc.qc_compare(vectors)
        qcvar[:] = flags


