import de_v1 from './translations_de.json';

// English source of truth for all UI strings used by V2. Keys mirror
// production_pilot/assets/translations_de.json 1:1 wherever V1 had an
// equivalent string, so the `de` export below can just spread that file
// instead of re-translating what already exists.
const en = {
  nav_dashboard: 'Dashboard',
  nav_statistics: 'Statistics',
  nav_service: 'Service',
  nav_settings: 'Settings',
  coming_soon: 'Coming soon',
  menu_tooltip: 'Access',
  auth_gate_title: 'Access Required',
  auth_gate_prompt: 'Enter password:',
  auth_gate_incorrect: 'Incorrect password.',
  block_view: 'Block View',
  list_view: 'List View',
  // Small label on top of the two-tier Next Action box (see TopBar.svelte);
  // the larger text below it is built from the next_action_* keys below.
  next_action_prefix: 'Next Action',
  next_action_error: '{unit}: Check Error',
  // A Ready machine is empty and needs loading now; an Almost Finished
  // (near-completion BAKING) one will need loading again soon once
  // unloaded — see nextAction.js's isNearDoneBaking/near_completion.
  next_action_load: '{unit}: Load',
  next_action_near_completion: '{unit}: Load Soon',
  no_action: '–',
  // Small corner badge on the one MachineTile matching the Next Action
  // banner (see FryerTile.svelte's isNext prop).
  tile_next_badge: 'Next',
  state_cold: 'Cold',
  state_heating: 'Heating',
  // Display label only — the underlying MachineState stays READY (colour,
  // priority logic, next-action wording all untouched). Renamed per spec
  // so the per-machine label matches kpi_waiting's existing wording below.
  state_ready: 'Waiting',
  state_baking: 'Baking',
  state_error: 'Error',
  state_near_completion: 'Almost finished',
  status_offline: 'Offline',
  status_online: 'Online',
  unit_fryer: 'Machine',
  // Shared wordy duration format used by every state timer — see
  // formatDuration in format.js. duration_hm_format kicks in once the
  // elapsed/remaining time reaches an hour (always "X hrs Y mins", no
  // singular/plural variants, matching duration_ms_format's style).
  duration_ms_format: '{mins} mins {secs} secs',
  duration_hm_format: '{h} hrs {m} mins',
  connection_lost: 'Connection lost — waiting for OPC UA server',
  theme_dark: 'Dark',
  theme_light: 'Light',
  display_size: 'Display Size',
  logout: 'Log out',
  settings_language: 'Language',
  settings_theme: 'Theme',
  settings_view: 'Dashboard View',

  kpi_busy: 'Busy',
  kpi_waiting: 'Waiting',
  kpi_error: 'Error',
  kpi_productivity: 'Productivity',
  kpi_no_data: '–',
  kpi_hm_format: '{h}h {m}m',

  list_col_status: 'Status',
  list_col_time: 'Time',
  list_col_recipe: 'Recipe',
  list_col_productivity: 'Productivity',

  stats_date_label: 'Date',
  stats_download_csv: 'Download CSV',
  stats_no_data: 'No data recorded for this date',
  stats_col_unit: 'Unit',
  stats_col_baking: 'Baking',
  stats_col_ready: 'Ready',
  stats_col_heating: 'Heating',
  stats_col_error: 'Error',
  stats_col_cold: 'Cold',
  stats_col_offline: 'Offline',
  stats_col_productivity: 'Productivity',
  stats_view_snapshot: 'Snapshot',
  stats_view_trend: 'Trend',
  stats_range_start: 'Start Date',
  stats_range_end: 'End Date',
  stats_axis_minutes: 'Minutes',
  stats_metric_baking: 'Baking',
  stats_metric_waiting: 'Waiting',
  stats_metric_error: 'Error',
  stats_metric_productivity: 'Productivity',
  stats_output_note: 'Output/production count requires additional PLC data not yet available.',

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
  service_change_password: 'Change Service Password',
  service_current_password: 'Current Password',
  service_new_password: 'New Password',
  service_confirm_password: 'Confirm New Password',
  service_save: 'Save',
  service_password_current_incorrect: 'The current password is incorrect.',
  service_password_empty: 'The new password must not be empty.',
  service_password_mismatch: 'New password and confirmation do not match.',
  service_change_management_password: 'Change Management Password',
  service_management_password_updated: 'Management password updated successfully.',
  service_password_updated: 'Password updated successfully.',
  service_too_many_attempts: 'Too many attempts. Please try again later.',
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
  wizard_rename_button: 'Rename',
  wizard_rename_placeholder: 'New machine name',
  wizard_remove_button: 'Remove',
  wizard_save_button: 'Save Configuration',
  wizard_confirm_button: 'Confirm',
  wizard_confirm_empty_title: 'Remove All Machines?',
  wizard_confirm_empty_message:
    'This will remove all machine configuration. The dashboard will show no machines until new ones are configured. Continue?',

  service_recording_heading: 'Data Recording',
  service_recording_toggle_label: 'Recording',
  service_recording_status_on: 'On',
  service_recording_status_off: 'Off',
  service_recording_summary_empty: 'No data recorded yet.',
  service_recording_row_count: '{n} row(s) recorded.',
  service_recording_earliest: 'Earliest',
  service_recording_latest: 'Latest',
  service_recording_clear_button: 'Clear History',
  service_recording_clear_confirm: 'This will permanently delete all recorded history. Continue?',
  service_recording_cleared: '{n} row(s) deleted.',

  // Service page layout — section headings grouping the cards below.
  service_section_setup: 'Setup',
  service_section_security: 'Security',
  service_section_data: 'Data',

  service_data_source_heading: 'Data Source',
  service_data_source_real: 'Real PLCs',
  service_data_source_demo: 'Demo Mode',
  service_data_source_error: 'Could not switch data source: {error}',
  service_demo_controls_heading: 'Demo Controls',
  service_demo_unit_col: 'Unit',
  service_demo_state_col: 'State',
  service_demo_recipe_col: 'Recipe',
  service_demo_recipe_none: '–',
  service_demo_online_col: 'Online',
  service_demo_remaining_col: 'Remaining (s)',
  service_demo_error: 'Could not update simulated state: {error}',

  stats_view_live: 'Live',
  stats_live_last_updated: 'Last updated {seconds}s ago',
  stats_live_recording_off:
    'Recording is currently off — no live data being captured. Enable it in Service settings to see live data here.',
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
  nav_statistics: 'Statistik',
  nav_settings: 'Einstellungen',
  menu_tooltip: 'Zugang',
  auth_gate_title: 'Zugang erforderlich',
  auth_gate_prompt: 'Passwort eingeben:',
  auth_gate_incorrect: 'Falsches Passwort.',
  // Overrides de_v1's old "{group} — {fryer}" format (single-line pill) —
  // the two-tier box now shows a plain label here and "{unit}: action"
  // below it (see next_action_prefix/error/load/near_completion above).
  next_action_prefix: 'Nächste Aktion',
  next_action_error: '{unit}: Störung prüfen',
  next_action_load: '{unit}: Beladen',
  next_action_near_completion: '{unit}: Bald beladen',
  tile_next_badge: 'Nächste',
  // Overrides de_v1's "Bereit" — same reasoning as the en export above.
  state_ready: 'Warte',
  state_near_completion: 'Fast fertig',
  theme_dark: 'Dunkel',
  theme_light: 'Hell',
  display_size: 'Anzeigegröße',
  logout: 'Abmelden',
  settings_language: 'Sprache',
  settings_theme: 'Thema',
  settings_view: 'Dashboard-Ansicht',

  kpi_busy: 'Beschäftigt',
  kpi_waiting: 'Warte',
  kpi_error: 'Störung',
  kpi_productivity: 'Produktivität',

  list_col_status: 'Status',
  list_col_time: 'Zeit',
  list_col_recipe: 'Rezept',
  list_col_productivity: 'Produktivität',

  stats_date_label: 'Datum',
  stats_download_csv: 'CSV herunterladen',
  stats_no_data: 'Keine Daten für dieses Datum erfasst',
  stats_col_unit: 'Einheit',
  stats_col_baking: 'Backen',
  stats_col_ready: 'Bereit',
  stats_col_heating: 'Aufheizen',
  stats_col_error: 'Fehler',
  stats_col_cold: 'Kalt',
  stats_col_offline: 'Offline',
  stats_col_productivity: 'Produktivität',
  stats_view_snapshot: 'Momentaufnahme',
  stats_view_trend: 'Trend',
  stats_range_start: 'Startdatum',
  stats_range_end: 'Enddatum',
  stats_axis_minutes: 'Minuten',
  stats_metric_baking: 'Backen',
  stats_metric_waiting: 'Wartezeit',
  stats_metric_error: 'Fehler',
  stats_metric_productivity: 'Produktivität',
  stats_output_note: 'Die Ausbringungs-/Stückzahlerfassung erfordert zusätzliche PLC-Daten, die noch nicht verfügbar sind.',

  // Keys V1 never had (no session/rate-limiting concept, and its wizard
  // used native OS message boxes where this web version uses inline
  // panels) — translated fresh, everything else above comes from de_v1.
  close: 'Schließen',
  back: 'Zurück',
  // Overrides de_v1's generic "Passwort ändern" now that there are two
  // distinct password forms on the Service page (see ChangePasswordCard
  // and ChangeManagementPasswordCard).
  service_change_password: 'Service-Passwort ändern',
  service_change_management_password: 'Management-Passwort ändern',
  service_management_password_updated: 'Management-Passwort erfolgreich aktualisiert.',
  service_too_many_attempts: 'Zu viele Versuche. Bitte später erneut versuchen.',
  service_config_saved: 'Konfiguration gespeichert.',
  service_config_save_failed: 'Konfiguration konnte nicht gespeichert werden: {error}',
  service_scan_error: 'Netzwerk-Scan fehlgeschlagen: {error}',
  wizard_subnet_label: 'Subnetz',
  wizard_port_label: 'Port',
  wizard_rename_button: 'Umbenennen',
  wizard_rename_placeholder: 'Neuer Maschinenname',
  wizard_confirm_button: 'Bestätigen',
  wizard_confirm_empty_title: 'Alle Maschinen entfernen?',
  wizard_confirm_empty_message:
    'Dies entfernt die gesamte Maschinenkonfiguration. Das Dashboard zeigt keine Maschinen an, bis neue konfiguriert werden. Fortfahren?',

  service_recording_heading: 'Datenaufzeichnung',
  service_recording_toggle_label: 'Aufzeichnung',
  service_recording_status_on: 'Ein',
  service_recording_status_off: 'Aus',
  service_recording_summary_empty: 'Noch keine Daten aufgezeichnet.',
  service_recording_row_count: '{n} Zeile(n) aufgezeichnet.',
  service_recording_earliest: 'Früheste',
  service_recording_latest: 'Letzte',
  service_recording_clear_button: 'Verlauf löschen',
  service_recording_clear_confirm: 'Dies löscht den gesamten aufgezeichneten Verlauf dauerhaft. Fortfahren?',
  service_recording_cleared: '{n} Zeile(n) gelöscht.',

  service_section_setup: 'Einrichtung',
  service_section_security: 'Sicherheit',
  service_section_data: 'Daten',

  service_data_source_heading: 'Datenquelle',
  service_data_source_real: 'Echte SPS',
  service_data_source_demo: 'Demo-Modus',
  service_data_source_error: 'Datenquelle konnte nicht gewechselt werden: {error}',
  service_demo_controls_heading: 'Demo-Steuerung',
  service_demo_unit_col: 'Einheit',
  service_demo_state_col: 'Status',
  service_demo_recipe_col: 'Rezept',
  service_demo_recipe_none: '–',
  service_demo_online_col: 'Online',
  service_demo_remaining_col: 'Restzeit (s)',
  service_demo_error: 'Simulierter Status konnte nicht aktualisiert werden: {error}',

  stats_view_live: 'Live',
  stats_live_last_updated: 'Zuletzt aktualisiert vor {seconds}s',
  stats_live_recording_off:
    'Die Aufzeichnung ist derzeit deaktiviert — es werden keine Live-Daten erfasst. Aktivieren Sie sie in den Service-Einstellungen, um hier Live-Daten zu sehen.',
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
