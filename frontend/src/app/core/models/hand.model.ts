/**
 * Types mirroring the backend's frozen HANDi EPN V3 specification.
 * Fetched at boot from `/hand/spec`, so the simulator and the validators can
 * never disagree about the hardware.
 */

export type ActuatorLetter = 'A' | 'B' | 'C' | 'D' | 'E' | 'F';
export type Handedness = 'right' | 'left';
export type JointTypeCode = 'R' | 'P' | 'I' | 'D';
export type LimitProfileId = 'TABLE_5_V3' | 'ANNEX_A_V3' | 'INTERSECTION';

export interface ActuatorSpec {
  letter: ActuatorLetter;
  label: string;
  digit: string;
  description: string;
  hardware: string;
  motor_shield_terminal: string;
  joints: string[];
}

export interface JointSpec {
  id: string;
  digit: string;
  joint_type: JointTypeCode;
  driven_by: ActuatorLetter;
  min_flexion_deg: number;
  max_flexion_deg: number;
  coupling: number;
  has_potentiometer: boolean;
  axis: string;
}

export interface GestureSpec {
  command: string;
  name: string;
  description: string;
  safety_class: 'motion' | 'gesture' | 'system' | 'emergency';
  pose: Record<ActuatorLetter, number> | null;
  typical_duration_ms: number;
}

export interface LimitProfileSpec {
  id: LimitProfileId;
  label: string;
  source: string;
  notes: string;
  limits: Record<ActuatorLetter, [number, number]>;
}

export interface HandSpec {
  driven_dof: number;
  kinematic_dof: number;
  potentiometer_count: number;
  fsr_count: number;
  actuators: ActuatorSpec[];
  joints: JointSpec[];
  gestures: GestureSpec[];
  limit_profiles: LimitProfileSpec[];
  protocol: Record<string, unknown>;
  safety: Record<string, number | boolean>;
  emg: {
    channel_count: number;
    channels: string[];
    sites: Record<string, string>;
    features: Record<string, string>;
    matrix_layout: string;
    amplitude_min: number;
    amplitude_max: number;
    default_samples: number;
    default_sample_rate_hz: number;
  };
}

/** A joint angle frame as broadcast by the backend. */
export interface JointAngle {
  joint_id: string;
  digit: string;
  joint_type: JointTypeCode;
  angle_deg: number;
  normalised: number;
  driven_by: ActuatorLetter;
}

/** A validated pose. The simulator only ever receives these. */
export interface MovementFrame {
  type?: 'movement';
  execution_id?: string;
  handedness: Handedness;
  limit_profile: string;
  source: string;
  serial_command: string | null;
  actuator_positions: Record<string, number>;
  actuator_normalised: Record<string, number>;
  joint_angles: JointAngle[];
  duration_ms: number;
}

export interface RejectionFrame {
  type: 'rejected';
  execution_id: string;
  status: string;
  failed_stage: string | null;
  reason: string;
}
