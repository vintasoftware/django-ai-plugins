import path from "node:path"
import { fileURLToPath } from "node:url"

const pluginDirectory = path.dirname(fileURLToPath(import.meta.url))
const skillsDirectory = path.resolve(pluginDirectory, "../../skills")

export const DjangoAiSkillsPlugin = async () => ({
  config: async (config) => {
    config.skills = config.skills || {}
    config.skills.paths = config.skills.paths || []
    if (!config.skills.paths.includes(skillsDirectory)) {
      config.skills.paths.push(skillsDirectory)
    }
  },
})

export default DjangoAiSkillsPlugin
