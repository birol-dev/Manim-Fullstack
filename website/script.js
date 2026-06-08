"use strict";

const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const header = document.querySelector(".site-header");
const navToggle = document.querySelector(".nav-toggle");
const navMenu = document.querySelector("#nav-menu");

function setHeaderState() {
  if (!header) return;
  header.classList.toggle("is-scrolled", window.scrollY > 18);
}

setHeaderState();
window.addEventListener("scroll", setHeaderState, { passive: true });

if (navToggle && navMenu) {
  navToggle.addEventListener("click", () => {
    const isOpen = navToggle.getAttribute("aria-expanded") === "true";
    navToggle.setAttribute("aria-expanded", String(!isOpen));
    navToggle.setAttribute("aria-label", isOpen ? "Open navigation menu" : "Close navigation menu");
    navMenu.classList.toggle("is-open", !isOpen);
    document.body.classList.toggle("nav-open", !isOpen);
  });

  navMenu.querySelectorAll("a").forEach((link) => {
    link.addEventListener("click", () => {
      navToggle.setAttribute("aria-expanded", "false");
      navToggle.setAttribute("aria-label", "Open navigation menu");
      navMenu.classList.remove("is-open");
      document.body.classList.remove("nav-open");
    });
  });
}

document.querySelectorAll(".faq-trigger").forEach((trigger) => {
  trigger.addEventListener("click", () => {
    const item = trigger.closest(".faq-item");
    if (!item) return;

    const willOpen = !item.classList.contains("is-open");
    document.querySelectorAll(".faq-item").forEach((faq) => {
      faq.classList.remove("is-open");
      const faqButton = faq.querySelector(".faq-trigger");
      faqButton?.setAttribute("aria-expanded", "false");
    });

    item.classList.toggle("is-open", willOpen);
    trigger.setAttribute("aria-expanded", String(willOpen));
  });
});

const revealTargets = document.querySelectorAll(
  ".pain-card, .workflow-board article, .feature-row, .table-row, .timeline article, .audience-grid article, .quote-panel, .faq-item, .download-panel"
);

if (prefersReducedMotion) {
  revealTargets.forEach((target) => target.classList.add("is-visible"));
} else if ("IntersectionObserver" in window) {
  const revealObserver = new IntersectionObserver(
    (entries) => {
      entries.forEach((entry) => {
        if (!entry.isIntersecting) return;
        entry.target.classList.add("is-visible");
        revealObserver.unobserve(entry.target);
      });
    },
    { threshold: 0.12, rootMargin: "0px 0px -80px 0px" }
  );

  revealTargets.forEach((target, index) => {
    target.classList.add("reveal");
    target.style.transitionDelay = `${Math.min(index * 28, 220)}ms`;
    revealObserver.observe(target);
  });
} else {
  revealTargets.forEach((target) => target.classList.add("is-visible"));
}

const launchForm = document.querySelector("#launch-form");
const emailInput = document.querySelector("#email");
const formStatus = document.querySelector("#form-status");

if (launchForm && emailInput && formStatus) {
  launchForm.addEventListener("submit", (event) => {
    event.preventDefault();
    formStatus.classList.remove("success", "error");

    if (!emailInput.value.trim() || !emailInput.validity.valid) {
      formStatus.textContent = "Enter a valid email address so the setup note has somewhere to land.";
      formStatus.classList.add("error");
      emailInput.focus();
      return;
    }

    const submitButton = launchForm.querySelector("button[type='submit']");
    if (submitButton) {
      submitButton.disabled = true;
      submitButton.textContent = "Sending…";
    }

    window.setTimeout(() => {
      formStatus.textContent = "Setup note queued locally. In the real app, this would hand off to your email service.";
      formStatus.classList.add("success");
      if (submitButton) {
        submitButton.disabled = false;
        submitButton.textContent = "Send The Note";
      }
      launchForm.reset();
    }, 620);
  });
}

const canvas = document.querySelector("#equation-field");
const context = canvas?.getContext("2d");

function resizeCanvas() {
  if (!canvas || !context) return;
  const ratio = Math.min(window.devicePixelRatio || 1, 2);
  const rect = canvas.getBoundingClientRect();
  canvas.width = Math.max(1, Math.floor(rect.width * ratio));
  canvas.height = Math.max(1, Math.floor(rect.height * ratio));
  context.setTransform(ratio, 0, 0, ratio, 0, 0);
}

const glyphs = [
  "∫",
  "∂",
  "π",
  "λ",
  "∑",
  "θ",
  "∇",
  "lim",
  "sin",
  "cos",
  "e^{iπ}",
  "MathTex",
  "Scene",
  "Write",
  "Transform",
];

let particles = [];
let animationFrame = 0;

function seedParticles() {
  if (!canvas) return;
  const rect = canvas.getBoundingClientRect();
  const count = Math.max(34, Math.min(80, Math.floor(rect.width / 22)));

  particles = Array.from({ length: count }, (_, index) => ({
    x: Math.random() * rect.width,
    y: Math.random() * rect.height,
    speed: 0.14 + Math.random() * 0.34,
    size: 13 + Math.random() * 18,
    alpha: 0.08 + Math.random() * 0.22,
    glyph: glyphs[index % glyphs.length],
    hue: index % 3,
  }));
}

function drawEquationField() {
  if (!canvas || !context) return;

  const rect = canvas.getBoundingClientRect();
  context.clearRect(0, 0, rect.width, rect.height);

  particles.forEach((particle) => {
    particle.y -= particle.speed;
    particle.x += Math.sin((particle.y + particle.size) / 90) * 0.12;

    if (particle.y < -40) {
      particle.y = rect.height + 40;
      particle.x = Math.random() * rect.width;
    }

    const color = particle.hue === 0 ? "240, 184, 77" : particle.hue === 1 ? "45, 167, 162" : "217, 107, 60";
    context.font = `${particle.size}px "JetBrains Mono", monospace`;
    context.fillStyle = `rgba(${color}, ${particle.alpha})`;
    context.fillText(particle.glyph, particle.x, particle.y);
  });

  animationFrame = window.requestAnimationFrame(drawEquationField);
}

if (canvas && context) {
  resizeCanvas();
  seedParticles();

  if (!prefersReducedMotion) {
    drawEquationField();
  } else {
    drawEquationField();
    window.cancelAnimationFrame(animationFrame);
  }

  window.addEventListener(
    "resize",
    () => {
      resizeCanvas();
      seedParticles();
      if (prefersReducedMotion) {
        drawEquationField();
        window.cancelAnimationFrame(animationFrame);
      }
    },
    { passive: true }
  );
}
