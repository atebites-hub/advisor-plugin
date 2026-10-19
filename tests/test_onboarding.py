"""The OpenAI setup entry point stays inside the single portable plugin."""

import json
from pathlib import Path
import unittest


REPOSITORY = Path(__file__).resolve().parents[1]
PLUGIN = REPOSITORY / "plugins/advisor"


class OnboardingTests(unittest.TestCase):
    def test_onboarding_points_to_a_packaged_namespaced_skill(self):
        manifest = json.loads((PLUGIN / "plugin.json").read_text())
        relative = manifest["extensions"]["com.openai"]["onboardingSkill"]
        self.assertEqual(relative, "./skills/advisor-setup/SKILL.md")
        skill = (PLUGIN / relative).resolve()
        self.assertTrue(skill.is_relative_to(PLUGIN.resolve()))
        self.assertTrue(skill.is_file())

    def test_setup_preserves_portable_identity_and_existing_components(self):
        manifest = json.loads((PLUGIN / "plugin.json").read_text())
        self.assertEqual(manifest["name"], "advisor")
        self.assertEqual(manifest["$schema"], "https://agent-plugins.org/schemas/1.0.0/plugin.schema.json")
        interface = manifest["extensions"]["com.openai"]["interface"]
        self.assertEqual(interface["displayName"], "Advisor")
        self.assertEqual(interface["category"], "Productivity")
        self.assertTrue((PLUGIN / "skills/advisor/SKILL.md").is_file())
        servers = json.loads((PLUGIN / "mcp.json").read_text())["mcpServers"]
        self.assertEqual(set(servers), {"advisor"})

    def test_marketplaces_still_distribute_only_the_advisor_package(self):
        for catalog in (".agents/plugins/marketplace.json", ".claude-plugin/marketplace.json",
                        ".cursor-plugin/marketplace.json"):
            with self.subTest(catalog=catalog):
                plugins = json.loads((REPOSITORY / catalog).read_text())["plugins"]
                self.assertEqual(len(plugins), 1)
                self.assertEqual(plugins[0]["name"], "advisor")
                source = plugins[0]["source"]
                path = source["path"] if isinstance(source, dict) else source
                self.assertEqual((REPOSITORY / path).resolve(), PLUGIN.resolve())


if __name__ == "__main__":
    unittest.main()
