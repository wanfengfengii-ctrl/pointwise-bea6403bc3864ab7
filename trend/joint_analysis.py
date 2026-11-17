"""Joint execution: one shared Z, all bindings conditioned together."""
from fractions import Fraction as F
from . import joint_math
from .joint import joint_task
from .calibration import calibration_revision as read_calibration
from .series import revision as read_series_revision
from .joint_reports import publish_joint, read_joint_report
from vendor.trend1 import Inconsistent


def analyze_joint(store, name):
    task = joint_task(store, name)
    if task['status'] == 'done':
        return read_joint_report(store, name)
    if task['status'] == 'error':
        raise Inconsistent(task['error'])
    calibration = read_calibration(store,
                                   task['calibration']['calibration_revision'])
    binding_specs, observations = [], []
    for binding in task['bindings']:
        revision = read_series_revision(store, binding['revision'])
        binding_specs.append({'id': binding['id'],
                              'state': revision['sdk1_state'],
                              'loading': F(binding['loading'])})
        observations.append(revision['observations'][:binding['prefix']])
    calibration_spec = {'mean': F(calibration['mean']),
                        'variance': F(calibration['variance'])}
    try:
        prior = joint_math.build_joint(binding_specs, calibration_spec)
        checkpoint = joint_math.condition_joint(
            prior, binding_specs, observations)
        report = joint_math.project_joint(checkpoint, task['queries'])
    except Inconsistent as exc:
        publish_joint(store, name, error=str(exc))
        raise
    publish_joint(store, name, result=report, checkpoint=checkpoint)
    return read_joint_report(store, name)
