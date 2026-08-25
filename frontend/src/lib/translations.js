import de_v1 from './translations_de.json';

// English source of truth for all UI strings used by V2. Keys mirror
// production_pilot/assets/translations_de.json 1:1 wherever V1 had an
// equivalent string, so the `de` export below can just spread that file
// instead of re-translating what already exists.
const en = {
  nav_dashboard: 'Dashboard',
  nav_service: 'Service',
  coming_soon: 'Coming soon',
  block_view: 'Block View',
  list_view: 'List View',
  next_action_prefix: 'Next action:',
  next_action_error: 'Check error: {group} — {fryer}',
  next_action_unload: 'Unload soon: {group} — {fryer}',
  next_action_load: 'Load: {group} — {fryer}',
  no_action: '–',
  state_cold: 'Cold',
  state_heating: 'Heating',
  state_ready: 'Ready',
  state_baking: 'Baking',
  state_error: 'Error',
  status_offline: 'Offline',
  status_online: 'Online',
  unit_fryer: 'Fryer',
  remaining_time_format: '{mins} mins {secs} secs',
  connection_lost: 'Connection lost — waiting for OPC UA server',
  theme_dark: 'Dark',
  theme_light: 'Light',
  display_size: 'Display Size',

  // Service tab — reused wherever V1's translations_de.json has a
  // matching key (see the `de` export below), written fresh here since
  // V1 only ever shipped German strings.
  cancel: 'Cancel',
  create: 'Create',
  close: 'Close',
  back: 'Back',
  unlock: 'Unlock',
  service_heading: 'Service',
  service_wizard_title: 'Installation Wizard',
  service_wizard_desc: 'Scan the network and group PLCs into machines.',
  service_change_password: 'Change Password',
  service_current_password: 'Current Password',
  service_new_password: 'New Password',
  service_confirm_password: 'Confirm New Password',
  service_save: 'Save',
  service_password_title: 'Service — Password Required',
  service_password_prompt: 'Enter service password:',
  service_password_incorrect: 'Incorrect password.',
  service_password_current_incorrect: 'The current password is incorrect.',
  service_password_empty: 'The new password must not be empty.',
  service_password_mismatch: 'New password and confirmation do not match.',
  service_password_updated: 'Password updated successfully.',
  service_too_many_attempts: 'Too many attempts. Please try again later.',
  service_session_expired: 'Session expired. Please log in again.',
  service_config_saved: 'Configuration saved.',
  service_config_save_failed: 'Could not save configuration: {error}',
  service_scan_error: 'Network scan failed: {error}',

  wizard_heading: 'Installation Wizard — Group PLCs into Machines',
  wizard_scan_section: '1. Scan Network',
  wizard_machines_section: '2. Machines',
  wizard_subnet_label: 'Subnet',
  wizard_port_label: 'Port',
  wizard_scan_button: 'Scan Network',
  wizard_scanning: 'Scanning …',
  wizard_found_devices: '{n} device(s) found.',
  wizard_no_devices_found: 'No devices found.',
  wizard_create_machine_button: '+  Create Machine from Selection',
  wizard_create_title: 'Create Machine',
  wizard_plcs_selected: '{n} PLC(s) selected:',
  wizard_machine_name_label: 'Machine name:',
  wizard_machine_name_placeholder: 'e.g. Fryer Station A',
  wizard_machine_type_label: 'Machine type:',
  wizard_priority_order_label: 'Priority order (top = highest priority)',
  wizard_move_up_button: 'Move Up',
  wizard_move_down_button: 'Move Down',
  wizard_name_required_msg: 'Please enter a name for this machine.',
  wizard_no_machines: 'No machines created yet.',
  wizard_remove_button: 'Remove',
  wizard_save_button: 'Save Configuration',
  wizard_confirm_button: 'Confirm',
  wizard_confirm_empty_title: 'Remove All Machines?',
  wizard_confirm_empty_message:
    'This will remove all machine configuration. The dashboard will show no machines until new ones are configured. Continue?',
};

// V1's JSON has a couple of stray non-breaking spaces before "…" that
// don't matter for V1 (Qt) but read oddly in a browser; harmless either
// way since we only pull the exact keys we use below.
const de = {
  ...en, // fallback for any key V1 never had (keeps both languages in sync)
  ...de_v1,
  // V1's connection_lost has a trailing " …" that this task's spec
  // explicitly writes without — use the exact string requested here.
  connection_lost: 'Verbindung unterbrochen — warte auf OPC-UA-Server',
  coming_soon: 'Demnächst verfügbar',
  next_action_prefix: 'Nächste Aktion:',
  theme_dark: 'Dunkel',
  theme_light: 'Hell',
  display_size: 'Anzeigegröße',

  // Keys V1 never had (no session/rate-limiting concept, and its wizard
  // used native OS message boxes where this web version uses inline
  // panels) — translated fresh, everything else above comes from de_v1.
  close: 'Schließen',
  back: 'Zurück',
  service_too_many_attempts: 'Zu viele Versuche. Bitte später erneut versuchen.',
  service_session_expired: 'Sitzung abgelaufen. Bitte erneut anmelden.',
  service_config_saved: 'Konfiguration gespeichert.',
  service_config_save_failed: 'Konfiguration konnte nicht gespeichert werden: {error}',
  service_scan_error: 'Netzwerk-Scan fehlgeschlagen: {error}',
  wizard_subnet_label: 'Subnetz',
  wizard_port_label: 'Port',
  wizard_confirm_button: 'Bestätigen',
  wizard_confirm_empty_title: 'Alle Maschinen entfernen?',
  wizard_confirm_empty_message:
    'Dies entfernt die gesamte Maschinenkonfiguration. Das Dashboard zeigt keine Maschinen an, bis neue konfiguriert werden. Fortfahren?',
};

export const translations = { en, de };

export function translate(lang, key, vars = {}) {
  const dict = translations[lang] ?? translations.en;
  let str = dict[key] ?? translations.en[key] ?? key;
  for (const [k, v] of Object.entries(vars)) {
    str = str.replaceAll(`{${k}}`, v);
  }
  return str;
}
