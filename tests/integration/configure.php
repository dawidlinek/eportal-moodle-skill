<?php
// Applies the site settings the integration tests rely on. Idempotent.
// Run inside the web container:  php /opt/moodle-it/configure.php
//
// Settings go through admin_write_settings(), the same path as the admin UI,
// so side effects run too: enabling the mobile service also enables the
// moodle_mobile_app external service, the REST protocol and the
// webservice/rest:use capability for authenticated users.

define('CLI_SCRIPT', true);

require('/var/www/html/config.php');
require_once($CFG->libdir . '/clilib.php');
require_once($CFG->libdir . '/adminlib.php');

$host = parse_url($CFG->wwwroot, PHP_URL_HOST);
if (!in_array($host, ['localhost', '127.0.0.1'], true)) {
    cli_error("Refusing to run: wwwroot {$CFG->wwwroot} is not a localhost site.");
}

\core\session\manager::set_user(get_admin());

$changed = admin_write_settings((object) [
    's__enablewebservices'      => '1',
    's__enablemobilewebservice' => '1',
    's__enablecompletion'       => '1',
    // 2 = "Via a browser window (for SSO plugins)": admin/tool/mobile/launch.php
    // then works over plain http.
    's_tool_mobile_typeoflogin' => '2',
]);

// Nothing on this site should ever send mail.
set_config('noemailever', 1);

// Verify the end state instead of trusting the write path.
$problems = [];
if (empty($CFG->enablewebservices)) {
    $problems[] = 'enablewebservices is off';
}
if (empty($CFG->enablemobilewebservice)) {
    $problems[] = 'enablemobilewebservice is off';
}
if (empty($CFG->enablecompletion)) {
    $problems[] = 'enablecompletion is off';
}
if ((int) get_config('tool_mobile', 'typeoflogin') !== 2) {
    $problems[] = 'tool_mobile/typeoflogin is not 2';
}
$protocols = array_filter(explode(',', $CFG->webserviceprotocols ?? ''));
if (!in_array('rest', $protocols, true)) {
    $problems[] = 'REST protocol is not enabled';
}
$service = $DB->get_record('external_services', ['shortname' => MOODLE_OFFICIAL_MOBILE_SERVICE]);
if (!$service || empty($service->enabled)) {
    $problems[] = 'moodle_mobile_app service is not enabled';
}
$authrole = $DB->get_record('role', ['id' => $CFG->defaultuserroleid], '*', MUST_EXIST);
$caps = role_context_capabilities($authrole->id, context_system::instance());
if (empty($caps['webservice/rest:use']) || $caps['webservice/rest:use'] != CAP_ALLOW) {
    $problems[] = 'webservice/rest:use is not allowed for authenticated users';
}

if ($problems) {
    cli_error('Configuration incomplete: ' . implode('; ', $problems));
}
mtrace("configure.php: OK ({$changed} setting(s) changed; web services, mobile service, REST, "
    . "completion on; tool_mobile/typeoflogin=2; noemailever=1)");
