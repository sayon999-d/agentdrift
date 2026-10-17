class Agentdrift < Formula
  include Language::Python::Virtualenv

  desc "Runtime supervisor and circuit breaker for autonomous coding agents"
  homepage "https://github.com/agentdrift/agentdrift"
  url "https://files.pythonhosted.org/packages/source/a/agentdrift/agentdrift-2.10.0.tar.gz"
  sha256 "REPLACE_WITH_ACTUAL_TAR_GZ_SHA256"
  license "MIT"
  head "https://github.com/agentdrift/agentdrift.git", branch: "main"

  depends_on "python@3.12"

  # Dependencies can be vendored via `resource` blocks when distributing
  # through homebrew-core or custom taps. Maintainers can generate resource
  # blocks automatically with:
  #   brew update-python-resources agentdrift
  # or using `homebrew-pypi-poet`:
  #   poet -f agentdrift

  def install
    virtualenv_install_with_resources
  end

  test do
    output = shell_output("#{bin}/agentdrift --help")
    assert_match "agentdrift", output.downcase
    assert_match "watch", output
    assert_match "health", output
  end
end
