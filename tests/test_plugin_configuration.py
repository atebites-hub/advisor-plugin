"""Native settings stay in the host manifest; portable MCP stays reusable."""
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1] / 'plugins/advisor'


class PluginConfigurationTests(unittest.TestCase):
    def test_zcode_native_settings_are_declared_and_forwarded_to_mcp(self):
        manifest = json.loads((ROOT / '.zcode-plugin/plugin.json').read_text())
        fields = manifest['userConfig']
        self.assertIs(fields['use_app_settings']['default'], True)
        env = manifest['mcpServers']['advisor']['env']
        self.assertEqual(env['ADVISOR_USE_APP_SETTINGS'], '${user_config.use_app_settings}')
        for provider in ('claude', 'codex'):
            for name, kind in (('enabled', 'boolean'), ('model', 'string'), ('effort', 'string')):
                key = provider + '_' + name
                self.assertEqual(fields[key]['type'], kind)
                self.assertEqual(env['ADVISOR_' + key.upper()], '${user_config.' + key + '}')
        self.assertEqual(manifest['mcpServers']['advisor']['args'],
                         ['run', '--script', '${ZCODE_PLUGIN_ROOT}/advisor.py', 'serve'])

    def test_portable_servers_do_not_reference_zcode_only_options(self):
        for path in (ROOT / 'mcp.json', ROOT / '.mcp.json', ROOT / '.cursor-plugin/mcp.json'):
            self.assertNotIn('user_config.', path.read_text())


if __name__ == '__main__':
    unittest.main()
